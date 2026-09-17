import { describe, expect, it } from "vitest";

import {
  AssessmentApiContractError,
  parseUi03GrowthHypothesisProjection,
  type AssessmentHumanTaskDecisionBody,
  type AssessmentHumanTaskDecisionReceipt,
  type ConfirmGrowthHypothesisBody,
  type GrowthHypothesisDecisionReceipt,
  type Ui03GrowthHypothesisProjection,
} from "../lib/family/assessment-api-contracts";
import {
  FamilyApiError,
  type StartGrowthOnboardingResponse,
} from "../lib/family/family-api-client";
import {
  Ui03FlowContractBlockedError,
  Ui03FlowPartialSuccessError,
  Ui03FlowStaleError,
  Ui03HumanTaskFlow,
  isRetryableUi03FlowError,
  type Ui03HumanTaskApi,
} from "../lib/family/ui03-human-task-flow";

describe("UI-03 two-step HumanTask flow", () => {
  it("orders human ACCEPT, complete-binding CONFIRM, and onboarding", async () => {
    const api = new RecordingApi();
    const flow = new Ui03HumanTaskFlow(api);

    const result = await flow.decide({
      token: "token-1",
      projection: projection(),
      outcome: "ACCEPT",
    });

    expect(api.calls.map((call) => call.kind)).toEqual([
      "human",
      "growth",
      "onboarding",
    ]);
    expect(api.calls[0]).toMatchObject({
      familyId: "family-1",
      taskId: "task-1",
      body: { outcome: "ACCEPT" },
    });
    expect(api.calls[1]).toMatchObject({
      body: {
        assessment_session_id: "assessment-family-1",
        hypothesis_ref: "hypothesis-family-1",
        decision_type: "CONFIRM",
        scope_ref: "family://tenant-1/family-1/assessment",
        signal_version: 3,
        reviewed_draft_ref: "draft-task-1",
        draft_version: 1,
        provenance_ref: "provenance-task-1",
        human_gate_receipt_ref: "task-1",
      },
    });
    expect(result).toEqual({
      status: "ONBOARDING_STARTED",
      familyId: "family-1",
      hypothesisRef: "hypothesis-family-1",
      humanTaskId: "task-1",
      subjectPersonId: "child-family-1",
      intentId: "intent-family-1",
      onboardingId: "onboarding-family-1",
    });
  });

  it("sends a reason-free REJECT and never invents an explanation", async () => {
    const api = new RecordingApi();
    const flow = new Ui03HumanTaskFlow(api);

    const result = await flow.decide({
      token: "token-1",
      projection: projection(),
      outcome: "REJECT",
    });
    expect(result.status).toBe("REJECTED");
    expect(api.calls).toHaveLength(1);
    expect(api.calls[0]).toMatchObject({
      kind: "human",
      body: { outcome: "REJECT" },
    });
    expect(
      (api.calls[0] as { body: AssessmentHumanTaskDecisionBody }).body,
    ).not.toHaveProperty("reason");
  });

  it("blocks 409 conflicts before CONFIRM or onboarding", async () => {
    const api = new RecordingApi();
    api.humanError = new FamilyApiError(
      "conflict",
      409,
      "assessment_human_task_expired",
      null,
    );
    const flow = new Ui03HumanTaskFlow(api);

    await expect(
      flow.decide({
        token: "token-1",
        projection: projection(),
        outcome: "ACCEPT",
      }),
    ).rejects.toBeInstanceOf(Ui03FlowContractBlockedError);
    expect(api.calls.map((call) => call.kind)).toEqual(["human"]);
  });

  it("retries a timeout with the original body and stable idempotency key", async () => {
    const api = new RecordingApi();
    api.humanError = new FamilyApiError(
      "timeout",
      0,
      "FAMILY_API_TIMEOUT",
      null,
    );
    const flow = new Ui03HumanTaskFlow(api);
    const input = {
      token: "token-1",
      projection: projection(),
      outcome: "ACCEPT" as const,
    };

    await expect(flow.decide(input)).rejects.toMatchObject({
      code: "FAMILY_API_TIMEOUT",
    });
    api.humanError = null;
    await expect(flow.decide(input)).resolves.toMatchObject({
      status: "ONBOARDING_STARTED",
    });

    const humanCalls = api.calls.filter((call) => call.kind === "human");
    expect(humanCalls).toHaveLength(2);
    expect(humanCalls[0]).toEqual(humanCalls[1]);
  });

  it("retries a timed-out non-adoption with the same reason-free body", async () => {
    const api = new RecordingApi();
    api.humanError = new FamilyApiError(
      "timeout",
      0,
      "FAMILY_API_TIMEOUT",
      null,
    );
    const flow = new Ui03HumanTaskFlow(api);
    const input = {
      token: "token-1",
      projection: projection(),
      outcome: "REJECT" as const,
    };

    await expect(flow.decide(input)).rejects.toMatchObject({
      code: "FAMILY_API_TIMEOUT",
    });
    api.humanError = null;
    await expect(flow.decide(input)).resolves.toMatchObject({
      status: "REJECTED",
    });

    const humanCalls = api.calls.filter((call) => call.kind === "human");
    expect(humanCalls).toHaveLength(2);
    expect(humanCalls[0]).toEqual(humanCalls[1]);
  });

  it("accepts a replayed growth receipt without starting a second logical flow", async () => {
    const api = new RecordingApi();
    api.growthReplayed = true;
    const flow = new Ui03HumanTaskFlow(api);

    const first = await flow.decide({
      token: "token-1",
      projection: projection(),
      outcome: "ACCEPT",
    });
    const replay = await flow.decide({
      token: "token-1",
      projection: projection(),
      outcome: "ACCEPT",
    });

    expect(first).toEqual(replay);
    const growthCalls = api.calls.filter((call) => call.kind === "growth");
    const onboardingCalls = api.calls.filter(
      (call) => call.kind === "onboarding",
    );
    expect(growthCalls[0]).toEqual(growthCalls[1]);
    expect(onboardingCalls[0]).toEqual(onboardingCalls[1]);
  });

  it("invalidates a late response when the active family changes", async () => {
    const api = new RecordingApi();
    const pending = deferred<AssessmentHumanTaskDecisionReceipt>();
    api.pendingHuman = pending.promise;
    const flow = new Ui03HumanTaskFlow(api);
    const oldFamily = flow.decide({
      token: "token-1",
      projection: projection(),
      outcome: "ACCEPT",
    });
    flow.bind(projection("family-2", "task-2"));
    pending.resolve(api.humanReceipt("family-1", "task-1", "ACCEPT"));

    await expect(oldFamily).rejects.toBeInstanceOf(Ui03FlowStaleError);
    expect(api.calls.map((call) => call.kind)).toEqual(["human"]);
  });

  it("never sends CONFIRM when the human receipt binding is absent", async () => {
    const api = new RecordingApi();
    api.omitAcceptedBinding = true;
    const flow = new Ui03HumanTaskFlow(api);

    await expect(
      flow.decide({
        token: "token-1",
        projection: projection(),
        outcome: "ACCEPT",
      }),
    ).rejects.toBeInstanceOf(Ui03FlowContractBlockedError);
    expect(api.calls.map((call) => call.kind)).toEqual(["human"]);
  });

  it.each(["FAMILY_API_TIMEOUT", "FAMILY_API_NETWORK_ERROR"] as const)(
    "preserves the HumanTask receipt for retryable %s GrowthIntent failures",
    async (code) => {
      const api = new RecordingApi();
      api.growthError = new FamilyApiError("network failure", 0, code, null);
      const flow = new Ui03HumanTaskFlow(api);
      const input = {
        token: "token-1",
        projection: projection(),
        outcome: "ACCEPT" as const,
      };

      const failure = await flow.decide(input).catch((error) => error);
      expect(failure).toBeInstanceOf(Ui03FlowPartialSuccessError);
      expect(failure).toMatchObject({
        stage: "HUMAN_ACCEPTED",
        humanReceipt: { task_id: "task-1", outcome: "ACCEPT" },
        growthReceipt: null,
        recovery: "RETRY_NETWORK",
      });
      expect(isRetryableUi03FlowError(failure)).toBe(true);

      api.growthError = null;
      await expect(flow.decide(input)).resolves.toMatchObject({
        status: "ONBOARDING_STARTED",
      });
      const humanCalls = api.calls.filter((call) => call.kind === "human");
      const growthCalls = api.calls.filter((call) => call.kind === "growth");
      expect(humanCalls[0]).toEqual(humanCalls[1]);
      expect(growthCalls[0]).toEqual(growthCalls[1]);
    },
  );

  it.each([
    [403, "HTTP_403", "PERMISSION_DENIED"],
    [404, "HTTP_404", "NOT_FOUND"],
    [409, "HTTP_409", "STATE_CHANGED"],
  ] as const)(
    "classifies a partial HTTP %i failure as non-retryable %s",
    async (status, code, recovery) => {
      const api = new RecordingApi();
      api.growthError = new FamilyApiError("blocked", status, code, null);

      const failure = await new Ui03HumanTaskFlow(api)
        .decide({
          token: "token-1",
          projection: projection(),
          outcome: "ACCEPT",
        })
        .catch((error) => error);

      expect(failure).toMatchObject({
        stage: "HUMAN_ACCEPTED",
        recovery,
      });
      expect(isRetryableUi03FlowError(failure)).toBe(false);
      expect(api.calls.map((call) => call.kind)).toEqual(["human", "growth"]);
    },
  );

  it("classifies a partial response contract mismatch as non-retryable", async () => {
    const api = new RecordingApi();
    api.growthError = new AssessmentApiContractError(
      "invalid growth receipt",
      null,
    );

    const failure = await new Ui03HumanTaskFlow(api)
      .decide({
        token: "token-1",
        projection: projection(),
        outcome: "ACCEPT",
      })
      .catch((error) => error);

    expect(failure).toMatchObject({
      stage: "HUMAN_ACCEPTED",
      recovery: "CONTRACT_MISMATCH",
    });
    expect(isRetryableUi03FlowError(failure)).toBe(false);
  });

  it("preserves the GrowthIntent receipt when onboarding fails", async () => {
    const api = new RecordingApi();
    api.onboardingError = new FamilyApiError(
      "unavailable",
      503,
      "HTTP_503",
      null,
    );
    const flow = new Ui03HumanTaskFlow(api);
    const input = {
      token: "token-1",
      projection: projection(),
      outcome: "ACCEPT" as const,
    };

    const failure = await flow.decide(input).catch((error) => error);
    expect(failure).toBeInstanceOf(Ui03FlowPartialSuccessError);
    expect(failure).toMatchObject({
      stage: "INTENT_CREATED",
      humanReceipt: { task_id: "task-1", outcome: "ACCEPT" },
      growthReceipt: {
        outcome: "INTENT_CREATED",
        intent: { intent_id: "intent-family-1" },
      },
    });

    api.onboardingError = null;
    await expect(flow.decide(input)).resolves.toMatchObject({
      onboardingId: "onboarding-family-1",
    });
    const onboardingCalls = api.calls.filter(
      (call) => call.kind === "onboarding",
    );
    expect(onboardingCalls[0]).toEqual(onboardingCalls[1]);
  });

  it.each(invalidOnboardingPayloads())(
    "fails closed after INTENT_CREATED when onboarding %s",
    async (_caseName, payload) => {
      const api = new RecordingApi();
      api.onboardingPayloadOverride = payload;

      const failure = await new Ui03HumanTaskFlow(api)
        .decide({
          token: "token-1",
          projection: projection(),
          outcome: "ACCEPT",
        })
        .catch((error) => error);

      expect(failure).toBeInstanceOf(Ui03FlowPartialSuccessError);
      expect(failure).toMatchObject({
        stage: "INTENT_CREATED",
        recovery: "CONTRACT_MISMATCH",
      });
      expect(api.calls.map((call) => call.kind)).toEqual([
        "human",
        "growth",
        "onboarding",
      ]);
    },
  );

  it("derives the same reason-free REJECT body and bounded key in new flow instances", async () => {
    const firstApi = new RecordingApi();
    const secondApi = new RecordingApi();

    await new Ui03HumanTaskFlow(firstApi).decide({
      token: "token-1",
      projection: projection(),
      outcome: "REJECT",
    });
    await new Ui03HumanTaskFlow(secondApi).decide({
      token: "token-1",
      projection: projection(),
      outcome: "REJECT",
    });

    expect(firstApi.calls).toEqual(secondApi.calls);
    expect(firstApi.calls).toHaveLength(1);
    expect(firstApi.calls[0]).toMatchObject({
      kind: "human",
      body: { outcome: "REJECT" },
    });
    expect(
      (firstApi.calls[0] as { body: AssessmentHumanTaskDecisionBody }).body,
    ).not.toHaveProperty("reason");
    expect(firstApi.calls.every((call) => call.key.length <= 128)).toBe(true);
  });

  it("invalidates late work when the hypothesis or HumanTask epoch changes", async () => {
    const api = new RecordingApi();
    const pending = deferred<AssessmentHumanTaskDecisionReceipt>();
    api.pendingHuman = pending.promise;
    const flow = new Ui03HumanTaskFlow(api);
    const oldHypothesis = flow.decide({
      token: "token-1",
      projection: projection(),
      outcome: "ACCEPT",
    });
    flow.bind(projection("family-1", "task-2", "hypothesis-2"));
    pending.resolve(api.humanReceipt("family-1", "task-1", "ACCEPT"));

    await expect(oldHypothesis).rejects.toBeInstanceOf(Ui03FlowStaleError);
    expect(api.calls.map((call) => call.kind)).toEqual(["human"]);
  });
});

type RecordedCall =
  | {
      kind: "human";
      familyId: string;
      taskId: string;
      body: AssessmentHumanTaskDecisionBody;
      key: string;
    }
  | {
      kind: "growth";
      familyId: string;
      body: ConfirmGrowthHypothesisBody;
      key: string;
    }
  | {
      kind: "onboarding";
      familyId: string;
      body: { intent_id: string };
      key: string;
      expectedSubjectPersonId: string;
    };

class RecordingApi implements Ui03HumanTaskApi {
  readonly calls: RecordedCall[] = [];
  humanError: unknown = null;
  growthError: unknown = null;
  onboardingError: unknown = null;
  onboardingPayloadOverride: unknown = null;
  pendingHuman: Promise<AssessmentHumanTaskDecisionReceipt> | null = null;
  omitAcceptedBinding = false;
  growthReplayed = false;

  async decideAssessmentHumanTask(
    _token: string,
    familyId: string,
    taskId: string,
    body: AssessmentHumanTaskDecisionBody,
    key: string,
  ): Promise<AssessmentHumanTaskDecisionReceipt> {
    this.calls.push({
      kind: "human",
      familyId,
      taskId,
      body: structuredClone(body),
      key,
    });
    if (this.humanError) throw this.humanError;
    if (this.pendingHuman) return this.pendingHuman;
    return this.humanReceipt(familyId, taskId, body.outcome);
  }

  async decideGrowthHypothesis(
    _token: string,
    familyId: string,
    body: ConfirmGrowthHypothesisBody,
    key: string,
  ): Promise<GrowthHypothesisDecisionReceipt> {
    this.calls.push({
      kind: "growth",
      familyId,
      body: structuredClone(body),
      key,
    });
    if (this.growthError) throw this.growthError;
    return {
      action: "CONFIRM_GROWTH_HYPOTHESIS",
      outcome: "INTENT_CREATED",
      hypothesis_ref: body.hypothesis_ref,
      intent: {
        intent_id: `intent-${familyId}`,
        need_type: "FAMILY_COMMUNICATION_SUPPORT",
        status: "OPEN",
        required_capability_keys: [],
        evidence_refs: [],
        boundary: "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME",
      },
      replayed: this.growthReplayed,
    };
  }

  async startGrowthOnboarding(
    _token: string,
    familyId: string,
    body: { intent_id: string },
    key: string,
    expectedSubjectPersonId: string,
  ): Promise<StartGrowthOnboardingResponse> {
    this.calls.push({
      kind: "onboarding",
      familyId,
      body: structuredClone(body),
      key,
      expectedSubjectPersonId,
    });
    if (this.onboardingError) throw this.onboardingError;
    return (this.onboardingPayloadOverride ??
      validOnboardingResponse(
        familyId,
        body.intent_id,
      )) as StartGrowthOnboardingResponse;
  }

  humanReceipt(
    familyId: string,
    taskId: string,
    outcome: "ACCEPT" | "REJECT",
  ): AssessmentHumanTaskDecisionReceipt {
    return {
      task_id: taskId,
      decision_id: `decision-${taskId}`,
      status: "DECIDED",
      outcome,
      reason: null,
      decided_at: "2026-09-17T00:00:00Z",
      binding:
        outcome === "ACCEPT" && !this.omitAcceptedBinding
          ? {
              subject_person_id: `child-${familyId}`,
              assessment_session_id: `assessment-${familyId}`,
              hypothesis_ref: `hypothesis-${familyId}`,
              scope_ref: `family://tenant-1/${familyId}/assessment`,
              signal_version: 3,
              reviewed_draft_ref: `draft-${taskId}`,
              draft_version: 1,
              provenance_ref: `provenance-${taskId}`,
              human_gate_receipt_ref: taskId,
            }
          : null,
    };
  }
}

function projection(
  familyId = "family-1",
  taskId = "task-1",
  hypothesisRef = `hypothesis-${familyId}`,
): Ui03GrowthHypothesisProjection {
  return parseUi03GrowthHypothesisProjection(
    {
      projection_version: "UI03_GROWTH_HYPOTHESIS_V1",
      tenant_id: "tenant-1",
      family_id: familyId,
      availability: "READY",
      latest_assessment_session_id: `assessment-${familyId}`,
      named_actions: {
        confirm: "CONFIRM_GROWTH_HYPOTHESIS",
        dismiss: "DISMISS_GROWTH_HYPOTHESIS",
      },
      ai_state: "MODEL_DRAFT_READY",
      hypothesis: {
        hypothesis_ref: hypothesisRef,
        subject_person_id: `child-${familyId}`,
        subject_display_name: "孩子",
        focus_ref: "COMMUNICATION",
        need_type_ref: "FAMILY_COMMUNICATION_SUPPORT",
        need_type_version: 1,
        title: "先看见沟通节奏",
        statement: "这是一项待验证支持假设。",
        required_capability_keys: [],
        source_refs: {
          assessment_session_id: `assessment-${familyId}`,
          assessment_response_id: `response-${familyId}`,
          assessment_evidence_id: `evidence-${familyId}`,
          tool_ref: "tool-1",
          tool_version: 3,
          assessment_submitted_at: null,
        },
        limitations: ["不是诊断"],
        generator: "FAMILY_EDUCATION_ASSESSMENT_MODEL_V0_1",
        model_draft_ref: `draft-${familyId}`,
        model_generator: "MODEL_GATEWAY",
        model_component_ref: "assessment-interpretation",
        model_boundary_labels: ["DRAFT_ONLY"],
        need_refs: [],
        construct_refs: [],
        action_candidate_refs: [],
        fact_boundary: "HYPOTHESIS_NOT_FACT_OR_DIAGNOSIS",
        scorecard: {
          generator: "MODEL_GATEWAY",
          agent_run_ref: `run-${familyId}`,
          provider_ref: "provider-1",
          model_ref: "model-1",
          model_version: "2026-09",
          prompt_version: "assessment.v1",
          schema_version: "assessment-result.v1",
          context_snapshot_ref: `context-${familyId}`,
          input_refs: [],
          draft_status: "DRAFT",
          human_task_ref: taskId,
          review_status: "REVIEW_REQUIRED",
        },
      },
    },
    familyId,
  );
}

function validOnboardingResponse(
  familyId: string,
  intentId: string,
): StartGrowthOnboardingResponse {
  const onboardingId = `onboarding-${familyId}`;
  const subjectPersonId = `child-${familyId}`;
  return {
    onboarding: {
      onboarding_id: onboardingId,
      tenant_id: "tenant-1",
      family_id: familyId,
      intent_id: intentId,
      subject_person_id: subjectPersonId,
      journey_type: "PARENT_CHILD_COMMUNICATION_CONFLICT",
      phase: "ONBOARDING",
      status: "ACTIVE",
      started_by_actor_id: "parent-1",
      started_at: "2026-09-17T00:00:00Z",
      version: 1,
      intent_binding: {
        binding_id: `binding-${familyId}`,
        tenant_id: "tenant-1",
        family_id: familyId,
        intent_id: intentId,
        onboarding_id: onboardingId,
        subject_person_id: subjectPersonId,
      },
    },
    event: {
      event_id: `event-${familyId}`,
      event_name: "GrowthOnboardingStarted",
      event_version: 1,
      tenant_id: "tenant-1",
      family_id: familyId,
      actor_id: "parent-1",
      intent_id: intentId,
      onboarding_id: onboardingId,
      subject_person_id: subjectPersonId,
      occurred_at: "2026-09-17T00:00:00Z",
    },
    created: true,
    replayed: false,
  };
}

function invalidOnboardingPayloads(): [string, unknown][] {
  const valid = validOnboardingResponse("family-1", "intent-family-1");
  const { event: _event, ...withoutEvent } = valid;
  const { occurred_at: _occurredAt, ...eventWithoutOccurredAt } = valid.event;
  const { started_at: _startedAt, ...onboardingWithoutStartedAt } =
    valid.onboarding;
  const { intent_binding: _intentBinding, ...onboardingWithoutBinding } =
    valid.onboarding;

  return [
    ["has a non-boolean created flag", { ...valid, created: "true" }],
    ["has a non-boolean replayed flag", { ...valid, replayed: 0 }],
    ["omits the event", withoutEvent],
    ["omits an event field", { ...valid, event: eventWithoutOccurredAt }],
    [
      "uses the wrong event field type",
      { ...valid, event: { ...valid.event, event_version: "1" } },
    ],
    [
      "is bound to another family",
      {
        ...valid,
        onboarding: { ...valid.onboarding, family_id: "family-2" },
      },
    ],
    [
      "is bound to another intent",
      {
        ...valid,
        onboarding: { ...valid.onboarding, intent_id: "intent-other" },
      },
    ],
    [
      "is bound to another subject",
      {
        ...valid,
        onboarding: {
          ...valid.onboarding,
          subject_person_id: "child-other",
        },
      },
    ],
    [
      "omits an onboarding field",
      { ...valid, onboarding: onboardingWithoutStartedAt },
    ],
    [
      "omits the intent binding",
      { ...valid, onboarding: onboardingWithoutBinding },
    ],
  ];
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => {
    resolve = next;
  });
  return { promise, resolve };
}
