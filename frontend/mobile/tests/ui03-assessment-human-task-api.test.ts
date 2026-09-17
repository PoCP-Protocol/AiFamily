import { describe, expect, it, vi } from "vitest";

import {
  AssessmentApiContractError,
  isUi03ReviewOpen,
  parseAssessmentHumanTaskDecisionReceipt,
  parseConfirmedGrowthHypothesisReceipt,
  parseUi03GrowthHypothesisProjection,
  type ConfirmGrowthHypothesisBody,
} from "../lib/family/assessment-api-contracts";
import { FamilyApiClient } from "../lib/family/family-api-client";

const projection = {
  projection_version: "UI03_GROWTH_HYPOTHESIS_V1",
  tenant_id: "tenant-1",
  family_id: "family-1",
  availability: "READY",
  latest_assessment_session_id: "assessment-1",
  named_actions: {
    confirm: "CONFIRM_GROWTH_HYPOTHESIS",
    dismiss: "DISMISS_GROWTH_HYPOTHESIS",
  },
  ai_state: "MODEL_DRAFT_READY",
  hypothesis: {
    hypothesis_ref: "ASSESSMENT:assessment-1:tool-1:v3:H1",
    subject_person_id: "child-1",
    subject_display_name: "孩子",
    focus_ref: "COMMUNICATION",
    need_type_ref: "FAMILY_COMMUNICATION_SUPPORT",
    need_type_version: 1,
    title: "先看见沟通节奏",
    statement: "这是一项需要家庭继续验证的支持假设。",
    required_capability_keys: ["family_dialogue"],
    source_refs: {
      assessment_session_id: "assessment-1",
      assessment_response_id: "response-1",
      assessment_evidence_id: "evidence-1",
      tool_ref: "tool-1",
      tool_version: 3,
      assessment_submitted_at: null,
    },
    limitations: ["不是诊断"],
    generator: "FAMILY_EDUCATION_ASSESSMENT_MODEL_V0_1",
    model_draft_ref: "draft-1",
    model_generator: "MODEL_GATEWAY",
    model_component_ref: "assessment-interpretation",
    model_boundary_labels: ["DRAFT_ONLY"],
    need_refs: [],
    construct_refs: [],
    action_candidate_refs: [],
    fact_boundary: "HYPOTHESIS_NOT_FACT_OR_DIAGNOSIS",
    scorecard: {
      generator: "MODEL_GATEWAY",
      agent_run_ref: "run-1",
      provider_ref: "provider-1",
      model_ref: "model-1",
      model_version: "2026-09",
      prompt_version: "assessment.v1",
      schema_version: "assessment-result.v1",
      context_snapshot_ref: "context-1",
      input_refs: ["evidence-1"],
      draft_status: "DRAFT",
      human_task_ref: "task-1",
      review_status: "REVIEW_REQUIRED",
    },
  },
} as const;

describe("UI-03 assessment HumanTask HTTP contract", () => {
  it("loads a REVIEW_REQUIRED Model Gateway projection as review-open", async () => {
    const fetcher = vi.fn(async () =>
      response(projection),
    ) as unknown as typeof fetch;
    const client = new FamilyApiClient("https://family.example", fetcher);

    const result = await client.getGrowthHypothesis("token-1", "family-1");

    expect(isUi03ReviewOpen(result)).toBe(true);
    if (!isUi03ReviewOpen(result))
      throw new Error("expected review-open UI-03");
    expect(result.hypothesis.scorecard.human_task_ref).toBe("task-1");
    expect(vi.mocked(fetcher).mock.calls[0][0]).toBe(
      "https://family.example/families/family-1/ui/03/growth-hypothesis",
    );
  });

  it("accepts governed deterministic and DRAFT_ONLY variants without opening review", () => {
    const deterministic = parseUi03GrowthHypothesisProjection(
      {
        ...projection,
        hypothesis: {
          ...projection.hypothesis,
          model_generator: "FAMILY_EDUCATION_MODEL_RUNTIME_DETERMINISTIC",
          scorecard: {
            generator: "FAMILY_EDUCATION_MODEL_RUNTIME_DETERMINISTIC",
          },
        },
      },
      "family-1",
    );
    expect(isUi03ReviewOpen(deterministic)).toBe(false);

    const draftOnly = parseUi03GrowthHypothesisProjection(
      {
        ...projection,
        hypothesis: {
          ...projection.hypothesis,
          scorecard: {
            ...projection.hypothesis.scorecard,
            human_task_ref: null,
            review_status: "DRAFT_ONLY",
          },
        },
      },
      "family-1",
    );
    expect(isUi03ReviewOpen(draftOnly)).toBe(false);
  });

  it("fails closed for missing, nullable, retired, or discriminator-mismatched fields", () => {
    const sourceWithoutSubmittedAt = {
      assessment_session_id: "assessment-1",
      assessment_response_id: "response-1",
      assessment_evidence_id: "evidence-1",
      tool_ref: "tool-1",
      tool_version: 3,
    };
    const invalidPayloads = [
      {
        ...projection,
        hypothesis: {
          ...projection.hypothesis,
          source_refs: sourceWithoutSubmittedAt,
        },
      },
      {
        ...projection,
        hypothesis: {
          ...projection.hypothesis,
          model_draft_ref: null,
        },
      },
      {
        ...projection,
        hypothesis: {
          ...projection.hypothesis,
          model_generator: "FAMILY_EDUCATION_MODEL_RUNTIME_GATEWAY",
        },
      },
      {
        ...projection,
        hypothesis: {
          ...projection.hypothesis,
          model_generator: "FAMILY_EDUCATION_MODEL_RUNTIME_DETERMINISTIC",
        },
      },
      {
        ...projection,
        hypothesis: {
          ...projection.hypothesis,
          scorecard: {
            ...projection.hypothesis.scorecard,
            generator: "FAMILY_EDUCATION_MODEL_RUNTIME_DETERMINISTIC",
          },
        },
      },
    ];

    for (const invalidPayload of invalidPayloads) {
      expect(() =>
        parseUi03GrowthHypothesisProjection(invalidPayload, "family-1"),
      ).toThrow(AssessmentApiContractError);
    }
  });

  it("fails closed for a missing receipt or a retired score model", () => {
    expect(() =>
      parseUi03GrowthHypothesisProjection(
        {
          ...projection,
          hypothesis: {
            ...projection.hypothesis,
            scorecard: {
              ...projection.hypothesis.scorecard,
              human_task_ref: null,
            },
          },
        },
        "family-1",
      ),
    ).toThrow(AssessmentApiContractError);

    expect(() =>
      parseUi03GrowthHypothesisProjection(
        {
          ...projection,
          hypothesis: {
            ...projection.hypothesis,
            scorecard: {
              ...projection.hypothesis.scorecard,
              overall_score: 99,
              dimensions: [],
            },
          },
        },
        "family-1",
      ),
    ).toThrow(AssessmentApiContractError);
  });

  it("rejects malicious receipt values instead of trusting array containers", () => {
    const expectedRejection = {
      familyId: "family-1",
      tenantId: "tenant-1",
      taskId: "task-1",
      outcome: "REJECT" as const,
      hypothesisRef: projection.hypothesis.hypothesis_ref,
      assessmentSessionId: "assessment-1",
      subjectPersonId: "child-1",
      signalVersion: 3,
    };
    expect(() =>
      parseAssessmentHumanTaskDecisionReceipt(
        {
          task_id: "task-1",
          decision_id: "decision-1",
          status: "DECIDED",
          outcome: "REJECT",
          reason: { injected: "not text" },
          decided_at: "2026-09-17T00:00:00Z",
          binding: null,
        },
        expectedRejection,
      ),
    ).toThrow(AssessmentApiContractError);

    expect(() =>
      parseAssessmentHumanTaskDecisionReceipt(
        {
          task_id: "task-1",
          decision_id: "decision-1",
          status: "DECIDED",
          outcome: "REJECT",
          decided_at: "2026-09-17T00:00:00Z",
          binding: null,
        },
        expectedRejection,
      ),
    ).toThrow(AssessmentApiContractError);

    expect(() =>
      parseConfirmedGrowthHypothesisReceipt(
        {
          action: "CONFIRM_GROWTH_HYPOTHESIS",
          outcome: "INTENT_CREATED",
          hypothesis_ref: projection.hypothesis.hypothesis_ref,
          intent: {
            intent_id: "intent-1",
            need_type: "FAMILY_COMMUNICATION_SUPPORT",
            status: "OPEN",
            required_capability_keys: ["family_dialogue", { injected: true }],
            evidence_refs: ["evidence-1"],
            boundary: "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME",
          },
          replayed: false,
        },
        projection.hypothesis.hypothesis_ref,
      ),
    ).toThrow(AssessmentApiContractError);

    expect(() =>
      parseConfirmedGrowthHypothesisReceipt(
        {
          action: "CONFIRM_GROWTH_HYPOTHESIS",
          outcome: "INTENT_CREATED",
          hypothesis_ref: projection.hypothesis.hypothesis_ref,
          intent: {
            intent_id: "intent-1",
            need_type: "FAMILY_COMMUNICATION_SUPPORT",
            status: "OPEN",
            required_capability_keys: [],
            evidence_refs: [42],
            boundary: "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME",
          },
          replayed: false,
        },
        projection.hypothesis.hypothesis_ref,
      ),
    ).toThrow(AssessmentApiContractError);
  });

  it("posts only ACCEPT/reason with Bearer and the stable Idempotency-Key", async () => {
    const fetcher = vi.fn(async () =>
      response({
        task_id: "task-1",
        decision_id: "decision-1",
        status: "DECIDED",
        outcome: "ACCEPT",
        reason: "我确认这是待验证方向",
        decided_at: "2026-09-17T00:00:00Z",
        binding: null,
      }),
    ) as unknown as typeof fetch;
    const client = new FamilyApiClient("https://family.example", fetcher);

    await client.decideAssessmentHumanTask(
      "token-1",
      "family-1",
      "task-1",
      { outcome: "ACCEPT", reason: "我确认这是待验证方向" },
      "human-task-key-1",
    );

    const [url, request] = vi.mocked(fetcher).mock.calls[0];
    expect(url).toBe(
      "https://family.example/families/family-1/assessment/human-tasks/task-1/decisions",
    );
    expect(request?.headers).toMatchObject({
      Authorization: "Bearer token-1",
      "Idempotency-Key": "human-task-key-1",
    });
    expect(JSON.parse(request?.body as string)).toEqual({
      outcome: "ACCEPT",
      reason: "我确认这是待验证方向",
    });
  });

  it("forwards the complete server binding to growth CONFIRM", async () => {
    const fetcher = vi.fn(async () =>
      response({
        action: "CONFIRM_GROWTH_HYPOTHESIS",
        outcome: "INTENT_CREATED",
        hypothesis_ref: projection.hypothesis.hypothesis_ref,
        intent: {
          intent_id: "intent-1",
          need_type: "FAMILY_COMMUNICATION_SUPPORT",
          status: "OPEN",
          required_capability_keys: [],
          evidence_refs: [],
          boundary: "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME",
        },
        replayed: false,
      }),
    ) as unknown as typeof fetch;
    const client = new FamilyApiClient("https://family.example", fetcher);
    const body: ConfirmGrowthHypothesisBody = {
      assessment_session_id: "assessment-1",
      hypothesis_ref: projection.hypothesis.hypothesis_ref,
      decision_type: "CONFIRM",
      scope_ref: "family://tenant-1/family-1/assessment",
      signal_version: 3,
      reviewed_draft_ref: "draft-1",
      draft_version: 1,
      provenance_ref: "provenance-1",
      human_gate_receipt_ref: "task-1",
    };

    await client.decideGrowthHypothesis(
      "token-1",
      "family-1",
      body,
      "growth-key-1",
    );

    const [url, request] = vi.mocked(fetcher).mock.calls[0];
    expect(url).toBe(
      "https://family.example/families/family-1/growth-hypotheses/decisions",
    );
    expect(JSON.parse(request?.body as string)).toEqual(body);
    expect(request?.headers).toMatchObject({
      Authorization: "Bearer token-1",
      "idempotency-key": "growth-key-1",
    });
  });
});

function response(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}
