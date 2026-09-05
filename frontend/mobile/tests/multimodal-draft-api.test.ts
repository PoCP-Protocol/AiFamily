import { describe, expect, it, vi } from "vitest";
import { FamilyApiClient, FamilyApiError } from "../lib/family/family-api-client";

const body = {
  run_id: "run-mobile-1",
  prompt_version: "experience-studio.v1",
  schema_version: "experience-draft.v1",
  payload: { expression: "今天的家庭互动" },
  output_schema: { type: "object", properties: { understanding: { type: "string" } } },
  modalities: ["TEXT"] as const,
  estimated_input_tokens: 8,
  strategy: "balanced" as const,
  input_refs: [],
  media_inputs: [],
};

const response = {
  run_id: "run-mobile-1",
  draft_id: "draft:run-mobile-1",
  provenance_ref: "model-draft:run-mobile-1",
  status: "DRAFT" as const,
  output: { understanding: "一份可讨论的理解", next_step: "先由家长确认" },
  requires_human_confirmation: true as const,
  scope: {
    tenant_id: "tenant-1", region_id: "CN", family_id: "family-1", subject_ids: ["guardian-1"],
    purpose: "family_growth_experience", consent_version: "v1", consent_granted: true as const,
    data_class: "FAMILY_PRIVATE_TEXT", locale: "zh-CN",
  },
  context_snapshot_ref: "snapshot-1",
  context_snapshot_expires_at: "2026-09-01T00:00:00Z",
  provenance: {
    provider_id: "synthetic-experience", model: "synthetic", model_version: "v1",
    prompt_version: "experience-studio.v1", schema_version: "experience-draft.v1",
    context_snapshot_ref: "snapshot-1", latency_ms: 2, data_class: "FAMILY_PRIVATE_TEXT",
    use_case: "family_growth_experience", confidence: null, generated_at: "2026-08-30T00:00:00Z",
  },
  route: {
    provider_id: "synthetic-experience", vendor: "internal", model: "synthetic", model_version: "v1",
    strategy: "balanced" as const, estimated_latency_ms: 10, estimated_cost_microusd: 0,
    fallback_provider_ids: [],
  },
};

const interaction = { run_id: "run-mobile-1", status: "accepted", interaction_ref: "interaction-1", idempotency_replayed: false };
const replay = {
  run_id: "run-mobile-1", status: "DRAFT" as const, state: "SUCCEEDED", event_sequence: 2,
  deletion_state: "active" as const, draft_payload: { understanding: "一份可讨论的理解" }, artifact_refs: [],
  entries: [{ event_id: "event-1", interaction_type: "DRAFT_CREATED", sequence: 1, payload: {}, occurred_at: "2026-08-30T00:00:00Z" }],
};

describe("FamilyApiClient multimodal draft contract", () => {
  it("sends only generation intent and maps a server DRAFT", async () => {
    const fetcher = vi.fn<typeof fetch>(async (_input, init) => new Response(JSON.stringify(response), { status: 200, headers: { "content-type": "application/json" } }));
    const client = new FamilyApiClient("https://api.example.test", fetcher as unknown as typeof fetch);
    const result = await client.createMultimodalDraft("token-1", "family-1", body, "idem-1");
    const [url, init] = fetcher.mock.calls[0];
    const sent = JSON.parse(String(init?.body));

    expect(url).toBe("https://api.example.test/families/family-1/experience/multimodal/drafts");
    expect(init?.headers).toMatchObject({ Authorization: "Bearer token-1", "idempotency-key": "idem-1" });
    expect(sent).toMatchObject({ run_id: "run-mobile-1", modalities: ["TEXT"], strategy: "balanced" });
    expect(sent).not.toHaveProperty("scope");
    expect(sent).not.toHaveProperty("provider_id");
    expect(sent).not.toHaveProperty("context_snapshot_ref");
    expect(result).toMatchObject({ run_id: "run-mobile-1", status: "DRAFT", requires_human_confirmation: true });
  });

  it("fails closed when the server response is malformed or scoped to another family", async () => {
    const malformed = { ...response, scope: { ...response.scope, family_id: "family-other" } };
    const fetcher = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(malformed), { status: 200 }));
    const client = new FamilyApiClient("https://api.example.test", fetcher as unknown as typeof fetch);
    await expect(client.createMultimodalDraft("token-1", "family-1", body, "idem-1"))
      .rejects.toMatchObject({ code: "MULTIMODAL_DRAFT_INVALID_RESPONSE", status: 502 });
  });

  it("preserves governed error codes from a fail-closed backend", async () => {
    const fetcher = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ detail: "multimodal_experience_runtime_not_configured" }), { status: 503 }));
    const client = new FamilyApiClient("https://api.example.test", fetcher as unknown as typeof fetch);
    await expect(client.createMultimodalDraft("token-1", "family-1", body, "idem-1"))
      .rejects.toMatchObject({ code: "multimodal_experience_runtime_not_configured", status: 503 });
  });

  it("keeps run_id and idempotency across decisions, feedback, human review, delete and replay", async () => {
    const fetcher = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(interaction), { status: 200 }));
    const client = new FamilyApiClient("https://api.example.test", fetcher as unknown as typeof fetch);
    const decision = await client.decideMultimodalRun("token-1", "family-1", "run-mobile-1", { decision: "confirm", draft_version: "experience-draft.v1" }, "idem-decision");
    const feedback = await client.recordMultimodalFeedback("token-1", "family-1", "run-mobile-1", { signal: "helpful", draft_version: "experience-draft.v1" }, "idem-feedback");
    const human = await client.requestMultimodalHumanReview("token-1", "family-1", "run-mobile-1", { reason: "需要人工解释" }, "idem-human");
    const deleted = await client.deleteMultimodalRun("token-1", "family-1", "run-mobile-1", "家长删除请求", "idem-delete");
    expect([decision, feedback, human, deleted]).toHaveLength(4);
    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
      "https://api.example.test/families/family-1/experience/multimodal/runs/run-mobile-1/decisions",
      "https://api.example.test/families/family-1/experience/multimodal/runs/run-mobile-1/feedback",
      "https://api.example.test/families/family-1/experience/multimodal/runs/run-mobile-1/human-review",
      "https://api.example.test/families/family-1/experience/multimodal/runs/run-mobile-1",
    ]);
    const [, deleteInit] = fetcher.mock.calls[3];
    expect(deleteInit?.method).toBe("DELETE");
    expect(deleteInit?.headers).toMatchObject({ "idempotency-key": "idem-delete" });

    const replayFetcher = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(replay), { status: 200 }));
    const replayClient = new FamilyApiClient("https://api.example.test", replayFetcher as unknown as typeof fetch);
    await expect(replayClient.replayMultimodalRun("token-1", "family-1", "run-mobile-1")).resolves.toMatchObject({ run_id: "run-mobile-1", event_sequence: 2 });
  });

  it("rejects malformed interaction and replay responses before UI state changes", async () => {
    const fetcher = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ run_id: "run-mobile-1", status: "accepted" }), { status: 200 }));
    const client = new FamilyApiClient("https://api.example.test", fetcher as unknown as typeof fetch);
    await expect(client.decideMultimodalRun("token-1", "family-1", "run-mobile-1", { decision: "reject" }, "idem-1"))
      .rejects.toMatchObject({ code: "MULTIMODAL_RUN_INTERACTION_INVALID_RESPONSE", status: 502 });
    await expect(client.replayMultimodalRun("token-1", "family-1", "run-mobile-1"))
      .rejects.toMatchObject({ code: "MULTIMODAL_RUN_REPLAY_INVALID_RESPONSE", status: 502 });

    const mismatchFetcher = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ ...interaction, run_id: "run-other" }), { status: 200 }));
    const mismatchClient = new FamilyApiClient("https://api.example.test", mismatchFetcher as unknown as typeof fetch);
    await expect(mismatchClient.recordMultimodalFeedback("token-1", "family-1", "run-mobile-1", { signal: "not_helpful" }, "idem-2"))
      .rejects.toMatchObject({ code: "MULTIMODAL_RUN_INTERACTION_INVALID_RESPONSE", status: 502 });
  });
});
