import {
  type CreateDraftInput,
  type DecisionReceipt,
  ExperienceApiError,
  type ExperienceApiClient,
  type ExperienceDraft,
  type FeedbackInput,
  type FeedbackReceipt,
  type HumanReviewInput,
  type HumanReviewReceipt,
  type DeletionReceipt,
  type ReplaySnapshot,
  type DraftDecisionInput,
} from "./client";

export type FakeScenario =
  | "success"
  | "consent_refused"
  | "provider_not_admitted"
  | "timeout_then_retry"
  | "human_review"
  | "deleted";

export class FakeExperienceApiClient implements ExperienceApiClient {
  private attempts = 0;
  private readonly decisions = new Map<string, DecisionReceipt>();

  constructor(private readonly scenario: FakeScenario = "success") {}

  async createDraft(input: CreateDraftInput, _idempotencyKey: string): Promise<ExperienceDraft> {
    if (!input.scope.consent_granted) {
      throw new ExperienceApiError("CONSENT_REQUIRED", "refused", "需要有效同意后才能理解这段表达。");
    }
    if (this.scenario === "consent_refused") {
      throw new ExperienceApiError("CONSENT_REQUIRED", "refused", "这次体验没有获得数据使用同意。");
    }
    if (this.scenario === "provider_not_admitted") {
      throw new ExperienceApiError("PROVIDER_NOT_ADMITTED", "refused", "当前模型尚未完成家庭数据准入。");
    }
    if (this.scenario === "deleted") {
      throw new ExperienceApiError("MEDIA_DELETED", "deleted", "图片引用已删除，无法继续读取。");
    }
    if (this.scenario === "timeout_then_retry" && this.attempts++ === 0) {
      throw new ExperienceApiError("TIMEOUT", "timeout", "模型响应超时，可以使用相同请求安全重试。");
    }
    const humanReview = this.scenario === "human_review";
    return {
      run_id: input.run_id,
      draft_version: "experience-draft.v1",
      status: "DRAFT",
      output: {
        understanding: humanReview
          ? "这是一份等待人工顾问进一步确认的理解草案。"
          : "我先把这段表达整理成一个可讨论的家庭情境。",
        next_step: "先确认这份理解是否贴近你的真实情况，再决定下一步。",
      },
      limitations: ["这不是事实结论，也不是诊断或评分。", "请在确认前检查证据和限制。"],
      provenance: {
        provenance_ref: `synthetic-provenance:${input.run_id}`,
        kind: "SYNTHETIC_TEST",
        model_attempt_ref: `synthetic-attempt:${input.run_id}`,
        context_snapshot_ref: input.context_snapshot_ref,
        prompt_version: input.prompt_version,
        schema_version: input.schema_version,
        captured_at: new Date().toISOString(),
      },
      requires_human_confirmation: true,
      media_inputs: input.media_inputs,
      correlation_id: `synthetic-correlation:${input.run_id}`,
    };
  }

  async decide(input: DraftDecisionInput, _idempotencyKey: string): Promise<DecisionReceipt> {
    const receipt: DecisionReceipt = {
      run_id: input.run_id,
      status: input.decision === "reject" ? "rejected" : "pending_human_confirmation",
      interaction_ref: `synthetic-interaction:${input.run_id}:decision`,
      idempotency_replayed: false,
    };
    this.decisions.set(input.run_id, receipt);
    return receipt;
  }

  async submitFeedback(input: FeedbackInput, _idempotencyKey: string): Promise<FeedbackReceipt> {
    return {
      run_id: input.run_id,
      status: "recorded",
      interaction_ref: `synthetic-interaction:${input.run_id}:feedback`,
      idempotency_replayed: false,
      recorded: true,
    };
  }

  async requestHuman(input: HumanReviewInput, _idempotencyKey: string): Promise<HumanReviewReceipt> {
    return {
      run_id: input.run_id,
      status: "human_review",
      interaction_ref: `synthetic-interaction:${input.run_id}:human-review`,
      idempotency_replayed: false,
    };
  }

  async deleteRun(runId: string, _idempotencyKey: string): Promise<DeletionReceipt> {
    return {
      run_id: runId,
      status: "deleted",
      interaction_ref: `synthetic-interaction:${runId}:delete`,
      idempotency_replayed: false,
    };
  }

  async replayRun(runId: string): Promise<ReplaySnapshot> {
    if (this.scenario === "deleted") {
      throw new ExperienceApiError("MEDIA_DELETED", "deleted", "这次体验已删除，无法回放。");
    }
    return {
      run_id: runId,
      status: "DRAFT",
      state: "SUCCEEDED",
      event_sequence: 3,
      deletion_state: "active",
      draft_payload: null,
      artifact_refs: [],
      entries: [
        { label: "表达已接收（仅保存引用）", at: "N0", event_id: `synthetic-event:${runId}:0`, sequence: 1 },
        { label: "AI 理解草案生成（DRAFT）", at: "N1", event_id: `synthetic-event:${runId}:1`, sequence: 2 },
        { label: "等待家庭确认或人工闸门", at: "N2", event_id: `synthetic-event:${runId}:2`, sequence: 3 },
      ],
    };
  }
}

export const createFakeExperienceApiClient = (scenario: FakeScenario = "success") =>
  new FakeExperienceApiClient(scenario);
