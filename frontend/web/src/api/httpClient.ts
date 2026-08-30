import {
  ExperienceApiError,
  type CreateDraftInput,
  type DecisionReceipt,
  type DraftDecisionInput,
  type ExperienceApiClient,
  type ExperienceDraft,
  type FeedbackInput,
  type FeedbackReceipt,
  type HumanReviewInput,
  type HumanReviewReceipt,
  type DeletionReceipt,
  type ReplaySnapshot,
} from "./client";

/**
 * Production seam placeholder. The first Sprint intentionally ships no
 * browser-side provider call; this client becomes the same-origin Experience
 * API adapter when the backend route is admitted.
 */
export class HttpExperienceApiClient implements ExperienceApiClient {
  private unavailable(): ExperienceApiError {
    return new ExperienceApiError(
      "PROVIDER_NOT_ADMITTED",
      "refused",
      "Experience API 尚未配置，当前不会在浏览器直接调用模型。",
    );
  }

  createDraft(_input: CreateDraftInput, _idempotencyKey: string): Promise<ExperienceDraft> {
    return Promise.reject(this.unavailable());
  }

  decide(_input: DraftDecisionInput, _idempotencyKey: string): Promise<DecisionReceipt> {
    return Promise.reject(this.unavailable());
  }

  submitFeedback(_input: FeedbackInput, _idempotencyKey: string): Promise<FeedbackReceipt> {
    return Promise.reject(this.unavailable());
  }

  requestHuman(_input: HumanReviewInput, _idempotencyKey: string): Promise<HumanReviewReceipt> {
    return Promise.reject(this.unavailable());
  }

  deleteRun(_runId: string, _idempotencyKey: string): Promise<DeletionReceipt> {
    return Promise.reject(this.unavailable());
  }

  replayRun(_runId: string): Promise<ReplaySnapshot> {
    return Promise.reject(this.unavailable());
  }
}
