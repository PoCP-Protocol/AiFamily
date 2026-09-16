import { describe, expect, it } from "vitest";

import {
  parseUi03GrowthHypothesisProjection,
  type AssessmentHumanTaskDecisionBody,
  type AssessmentHumanTaskDecisionReceipt,
  type ConfirmGrowthHypothesisBody,
  type GrowthHypothesisDecisionReceipt,
  type Ui03GrowthHypothesisProjection,
} from "../lib/family/assessment-api-contracts";
import { FamilyApiError } from "../lib/family/family-api-client";
import {
  Ui03FlowContractBlockedError,
  Ui03FlowStaleError,
  Ui03HumanTaskFlow,
  type Ui03HumanTaskApi,
} from "../lib/family/ui03-human-task-flow";

describe("UI-03 two-step HumanTask flow", () => {
  it("orders human ACCEPT, complete-binding CONFIRM, and onboarding", async () => {
    const api = new RecordingApi();
    const flow = new Ui03HumanTaskFlow(api, (prefix) => `${prefix}-stable`);

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

  it("requires a real REJECT reason and terminates without growth decision", async () => {
    const api = new RecordingApi();
    const flow = new Ui03HumanTaskFlow(api);

    await expect(
      flow.decide({
        token: "token-1",
        projection: projection(),
        outcome: "REJECT",
        reason: "   ",
      }),
    ).rejects.toBeInstanceOf(Ui03FlowContractBlockedError);
    expect(api.calls).toHaveLength(0);

    const result = await flow.decide({
      token: "token-1",
      projection: projection(),
      outcome: "REJECT",
      reason: "  这与我们的真实观察不一致  ",
    });
    expect(result.status).toBe("REJECTED");
    expect(api.calls).toHaveLength(1);
    expect(api.calls[0]).toMatchObject({
      kind: "human",
      body: { outcome: "REJECT", reason: "这与我们的真实观察不一致" },
    });
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
    let sequence = 0;
    const flow = new Ui03HumanTaskFlow(
      api,
      (prefix) => `${prefix}-${++sequence}`,
    );
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

  it("accepts a replayed growth receipt without starting a second logical flow", async () => {
    const api = new RecordingApi();
    api.growthReplayed = true;
    const flow = new Ui03HumanTaskFlow(api, (prefix) => `${prefix}-stable`);

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
    };

class RecordingApi implements Ui03HumanTaskApi {
  readonly calls: RecordedCall[] = [];
  humanError: unknown = null;
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
    return this.humanReceipt(familyId, taskId, body.outcome, body.reason);
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

  async startGrowthOnboarding<T>(
    _token: string,
    familyId: string,
    body: { intent_id: string },
    key: string,
  ): Promise<T> {
    this.calls.push({
      kind: "onboarding",
      familyId,
      body: structuredClone(body),
      key,
    });
    return { onboarding: { onboarding_id: `onboarding-${familyId}` } } as T;
  }

  humanReceipt(
    familyId: string,
    taskId: string,
    outcome: "ACCEPT" | "REJECT",
    reason?: string,
  ): AssessmentHumanTaskDecisionReceipt {
    return {
      task_id: taskId,
      decision_id: `decision-${taskId}`,
      status: "DECIDED",
      outcome,
      reason: outcome === "REJECT" ? (reason ?? "rejected") : null,
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
        hypothesis_ref: `hypothesis-${familyId}`,
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
        },
        limitations: ["不是诊断"],
        generator: "FAMILY_EDUCATION_ASSESSMENT_MODEL_V0_1",
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

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => {
    resolve = next;
  });
  return { promise, resolve };
}
