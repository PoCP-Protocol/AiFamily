import {
  AssessmentApiContractError,
  parseAssessmentHumanTaskDecisionReceipt,
  parseConfirmedGrowthHypothesisReceipt,
  type AssessmentHumanTaskDecisionBody,
  type AssessmentHumanTaskDecisionReceipt,
  type ConfirmGrowthHypothesisBody,
  type GrowthHypothesisDecisionReceipt,
  type Ui03GrowthHypothesisProjection,
} from "./assessment-api-contracts";
import { FamilyApiError } from "./family-api-client";

export interface Ui03HumanTaskApi {
  decideAssessmentHumanTask(
    token: string,
    familyId: string,
    taskId: string,
    body: AssessmentHumanTaskDecisionBody,
    idempotencyKey: string,
  ): Promise<AssessmentHumanTaskDecisionReceipt>;
  decideGrowthHypothesis(
    token: string,
    familyId: string,
    body: ConfirmGrowthHypothesisBody,
    idempotencyKey: string,
  ): Promise<GrowthHypothesisDecisionReceipt>;
  startGrowthOnboarding<T>(
    token: string,
    familyId: string,
    body: { intent_id: string },
    idempotencyKey: string,
  ): Promise<T>;
}

export interface Ui03FlowContext {
  familyId: string;
  hypothesisRef: string;
  humanTaskId: string;
  subjectPersonId: string;
  intentId: string;
  onboardingId: string;
}

export type Ui03HumanDecisionResult =
  | {
      status: "REJECTED";
      familyId: string;
      hypothesisRef: string;
      humanTaskId: string;
    }
  | ({ status: "ONBOARDING_STARTED" } & Ui03FlowContext);

export class Ui03FlowStaleError extends Error {
  readonly code = "UI03_STALE_OPERATION";

  constructor() {
    super(
      "UI-03 operation no longer belongs to the active family and hypothesis",
    );
    this.name = "Ui03FlowStaleError";
  }
}

export class Ui03FlowContractBlockedError extends Error {
  readonly code = "UI03_CONTRACT_BLOCKED";

  constructor(
    message: string,
    readonly causeValue: unknown,
  ) {
    super(message);
    this.name = "Ui03FlowContractBlockedError";
  }
}

export type Ui03PartialSuccessStage = "HUMAN_ACCEPTED" | "INTENT_CREATED";

export class Ui03FlowPartialSuccessError extends Error {
  readonly code = "UI03_PARTIAL_SUCCESS";

  constructor(
    readonly stage: Ui03PartialSuccessStage,
    readonly humanReceipt: AssessmentHumanTaskDecisionReceipt,
    readonly growthReceipt: GrowthHypothesisDecisionReceipt | null,
    readonly causeValue: unknown,
  ) {
    super(
      stage === "HUMAN_ACCEPTED"
        ? "HumanTask was accepted but GrowthIntent was not created"
        : "GrowthIntent was created but onboarding was not started",
    );
    this.name = "Ui03FlowPartialSuccessError";
  }
}

/**
 * Coordinates the two human-confirmation writes without owning business data.
 * Every write uses a deterministic key derived from its immutable scope and
 * body. A remounted component therefore replays the same request safely.
 */
export class Ui03HumanTaskFlow {
  private revision = 0;
  private activeScopeKey: string | null = null;

  constructor(private readonly api: Ui03HumanTaskApi) {}

  bind(projection: Ui03GrowthHypothesisProjection): void {
    const scopeKey = projectionScopeKey(projection);
    if (this.activeScopeKey !== scopeKey) {
      this.revision += 1;
      this.activeScopeKey = scopeKey;
    }
  }

  invalidate(): void {
    this.revision += 1;
    this.activeScopeKey = null;
  }

  async decide(input: {
    token: string;
    projection: Ui03GrowthHypothesisProjection;
    outcome: "ACCEPT" | "REJECT";
    reason?: string;
  }): Promise<Ui03HumanDecisionResult> {
    this.bind(input.projection);
    const hypothesis = readyHypothesis(input.projection);
    const familyId = input.projection.family_id;
    const taskId = hypothesis.scorecard.human_task_ref;
    const scopeKey = projectionScopeKey(input.projection);
    const operationRevision = this.revision;
    const reason = input.reason?.trim();

    const decisionBody: AssessmentHumanTaskDecisionBody = Object.freeze({
      outcome: input.outcome,
      ...(reason ? { reason } : {}),
    });
    const humanDecisionFingerprint = [
      scopeKey,
      input.outcome,
      reason ?? "",
    ].join(":");
    const humanDecisionKey = createUi03IdempotencyKey(
      "ui03-human-task-decision",
      humanDecisionFingerprint,
    );

    let humanReceipt: AssessmentHumanTaskDecisionReceipt;
    try {
      const rawHumanReceipt = await this.api.decideAssessmentHumanTask(
        input.token,
        familyId,
        taskId,
        decisionBody,
        humanDecisionKey,
      );
      this.assertCurrent(operationRevision, scopeKey);
      humanReceipt = parseAssessmentHumanTaskDecisionReceipt(rawHumanReceipt, {
        familyId,
        tenantId: input.projection.tenant_id,
        taskId,
        outcome: input.outcome,
        hypothesisRef: hypothesis.hypothesis_ref,
        assessmentSessionId: hypothesis.source_refs.assessment_session_id,
        subjectPersonId: hypothesis.subject_person_id,
        signalVersion: hypothesis.source_refs.tool_version,
      });
    } catch (error) {
      this.throwBeforeHumanReceipt(error, operationRevision, scopeKey);
    }

    if (input.outcome === "REJECT") {
      return {
        status: "REJECTED",
        familyId,
        hypothesisRef: hypothesis.hypothesis_ref,
        humanTaskId: taskId,
      };
    }

    const binding = humanReceipt.binding;
    if (!binding) {
      throw new Ui03FlowPartialSuccessError(
        "HUMAN_ACCEPTED",
        humanReceipt,
        null,
        new AssessmentApiContractError(
          "accepted receipt is missing its binding",
          humanReceipt,
        ),
      );
    }
    const confirmationBody: ConfirmGrowthHypothesisBody = Object.freeze({
      assessment_session_id: binding.assessment_session_id,
      hypothesis_ref: binding.hypothesis_ref,
      decision_type: "CONFIRM",
      scope_ref: binding.scope_ref,
      signal_version: binding.signal_version,
      reviewed_draft_ref: binding.reviewed_draft_ref,
      draft_version: binding.draft_version,
      provenance_ref: binding.provenance_ref,
      human_gate_receipt_ref: binding.human_gate_receipt_ref,
    });
    const growthDecisionKey = createUi03IdempotencyKey(
      "ui03-growth-confirmation",
      `${scopeKey}:${JSON.stringify(confirmationBody)}`,
    );

    let growthReceipt: GrowthHypothesisDecisionReceipt;
    let intentId: string;
    try {
      const rawGrowthReceipt = await this.api.decideGrowthHypothesis(
        input.token,
        familyId,
        confirmationBody,
        growthDecisionKey,
      );
      this.assertCurrent(operationRevision, scopeKey);
      growthReceipt = parseConfirmedGrowthHypothesisReceipt(
        rawGrowthReceipt,
        hypothesis.hypothesis_ref,
      );
      const createdIntentId = growthReceipt.intent?.intent_id;
      intentId = createdIntentId ?? "";
      if (!intentId) {
        throw new AssessmentApiContractError(
          "INTENT_CREATED receipt is missing intent_id",
          growthReceipt,
        );
      }
    } catch (error) {
      if (error instanceof Ui03FlowStaleError) throw error;
      throw new Ui03FlowPartialSuccessError(
        "HUMAN_ACCEPTED",
        humanReceipt,
        null,
        error,
      );
    }

    const onboardingKey = createUi03IdempotencyKey(
      "ui03-start-onboarding",
      `${scopeKey}:${intentId}`,
    );
    try {
      const rawOnboarding = await this.api.startGrowthOnboarding<unknown>(
        input.token,
        familyId,
        Object.freeze({ intent_id: intentId }),
        onboardingKey,
      );
      this.assertCurrent(operationRevision, scopeKey);
      const onboardingId = readOnboardingId(rawOnboarding);
      return {
        status: "ONBOARDING_STARTED",
        familyId,
        hypothesisRef: hypothesis.hypothesis_ref,
        humanTaskId: taskId,
        subjectPersonId: hypothesis.subject_person_id,
        intentId,
        onboardingId,
      };
    } catch (error) {
      if (error instanceof Ui03FlowStaleError) throw error;
      throw new Ui03FlowPartialSuccessError(
        "INTENT_CREATED",
        humanReceipt,
        growthReceipt,
        error,
      );
    }
  }

  private throwBeforeHumanReceipt(
    error: unknown,
    operationRevision: number,
    scopeKey: string,
  ): never {
    if (
      error instanceof Ui03FlowStaleError ||
      isRetryableUi03FlowError(error)
    ) {
      throw error;
    }
    if (
      this.revision === operationRevision &&
      this.activeScopeKey === scopeKey
    ) {
      this.invalidate();
    }
    if (error instanceof Ui03FlowContractBlockedError) throw error;
    throw new Ui03FlowContractBlockedError(
      "UI-03 confirmation contract was blocked before a receipt was verified",
      error,
    );
  }

  private assertCurrent(revision: number, scopeKey: string): void {
    if (this.revision !== revision || this.activeScopeKey !== scopeKey) {
      throw new Ui03FlowStaleError();
    }
  }
}

export function isRetryableUi03FlowError(error: unknown): boolean {
  if (error instanceof Ui03FlowPartialSuccessError) {
    return isRetryableUi03FlowError(error.causeValue);
  }
  return (
    error instanceof FamilyApiError &&
    error.status === 0 &&
    (error.code === "FAMILY_API_TIMEOUT" ||
      error.code === "FAMILY_API_NETWORK_ERROR")
  );
}

export function createUi03IdempotencyKey(
  prefix: string,
  fingerprint: string,
): string {
  const boundedPrefix = prefix.replace(/[^a-zA-Z0-9_-]/g, "-").slice(0, 80);
  return `${boundedPrefix}-${hashFingerprint(fingerprint)}`;
}

function hashFingerprint(value: string): string {
  let first = 0x811c9dc5;
  let second = 0x9e3779b9;
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    first = Math.imul(first ^ code, 0x01000193);
    second = Math.imul(second ^ code, 0x85ebca6b);
    second ^= second >>> 13;
  }
  return [first, second]
    .map((part) => (part >>> 0).toString(16).padStart(8, "0"))
    .join("");
}

function projectionScopeKey(
  projection: Ui03GrowthHypothesisProjection,
): string {
  const hypothesis = readyHypothesis(projection);
  return [
    projection.family_id,
    hypothesis.hypothesis_ref,
    hypothesis.scorecard.human_task_ref,
  ].join(":");
}

function readyHypothesis(
  projection: Ui03GrowthHypothesisProjection,
): NonNullable<Ui03GrowthHypothesisProjection["hypothesis"]> {
  if (projection.availability !== "READY" || !projection.hypothesis) {
    throw new Ui03FlowContractBlockedError(
      "UI-03 has no reviewable hypothesis",
      projection,
    );
  }
  const taskId = projection.hypothesis.scorecard?.human_task_ref;
  if (typeof taskId !== "string" || !taskId.trim()) {
    throw new Ui03FlowContractBlockedError(
      "UI-03 is missing scorecard.human_task_ref",
      projection,
    );
  }
  return projection.hypothesis;
}

function readOnboardingId(payload: unknown): string {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new AssessmentApiContractError(
      "onboarding receipt must be an object",
      payload,
    );
  }
  const onboarding = (payload as Record<string, unknown>).onboarding;
  if (
    !onboarding ||
    typeof onboarding !== "object" ||
    Array.isArray(onboarding)
  ) {
    throw new AssessmentApiContractError(
      "onboarding receipt is missing onboarding",
      payload,
    );
  }
  const onboardingId = (onboarding as Record<string, unknown>).onboarding_id;
  if (typeof onboardingId !== "string" || !onboardingId.trim()) {
    throw new AssessmentApiContractError(
      "onboarding receipt is missing onboarding_id",
      payload,
    );
  }
  return onboardingId;
}
