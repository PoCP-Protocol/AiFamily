import { describe, expect, it, vi } from "vitest";
import { HttpExperienceApiClient } from "./httpClient";
import type { CreateDraftInput } from "./client";

const input: CreateDraftInput = {
  run_id: "run-1",
  use_case: "family_expression_understanding",
  prompt_version: "experience-studio.v1",
  schema_version: "experience-draft.v1",
  data_class: "FAMILY_PRIVATE_TEXT",
  context_snapshot_ref: "client-must-not-send",
  payload: { expression: "最近我们总在催促中争吵。" },
  input_refs: ["media:one"],
  media_inputs: [{ media_type: "IMAGE", uri: "media:one", mime_type: "image/png", sha256: "hash" }],
  scope: {
    tenant_id: "tenant",
    region_id: "CN",
    family_id: "family-1",
    subject_ids: ["guardian"],
    purpose: "family_growth_experience",
    consent_version: "v1",
    consent_granted: true,
    locale: "zh-CN",
  },
};

const responseBody = {
  run_id: "run-1",
  status: "DRAFT",
  output: { understanding: "一份理解", next_step: "先核对", limitations: ["不是事实"] },
  requires_human_confirmation: true,
  scope: {
    tenant_id: "tenant", region_id: "CN", family_id: "family-1", subject_ids: ["guardian"],
    purpose: "family_growth_experience", consent_version: "v1", consent_granted: true,
    data_class: "FAMILY_PRIVATE_TEXT", locale: "zh-CN",
  },
  context_snapshot_ref: "server-snapshot",
  context_snapshot_expires_at: "2026-09-01T00:00:00Z",
  provenance: {
    provider_id: "approved-provider", model: "model", model_version: "model-v1",
    prompt_version: "experience-studio.v1", schema_version: "experience-draft.v1",
    context_snapshot_ref: "server-snapshot", latency_ms: 420, data_class: "FAMILY_PRIVATE_TEXT",
    use_case: "family_growth_experience", confidence: 0.8, generated_at: "2026-08-30T00:00:00Z",
  },
  route: {
    provider_id: "approved-provider", vendor: "vendor", model: "model", model_version: "model-v1",
    strategy: "balanced", estimated_latency_ms: 500, estimated_cost_microusd: 10,
    fallback_provider_ids: [],
  },
};

describe("HttpExperienceApiClient", () => {
  it("sends only the backend generation body and maps a DRAFT response", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(responseBody), { status: 200 }));
    const client = new HttpExperienceApiClient({ baseUrl: "https://api.example.test", fetchImpl });
    const draft = await client.createDraft(input, "idem-1");
    const [url, init] = fetchImpl.mock.calls[0];
    const body = JSON.parse(String(init?.body));

    expect(url).toBe("https://api.example.test/families/family-1/experience/multimodal/drafts");
    expect(init?.headers).toMatchObject({ "content-type": "application/json", "x-idempotency-key": "idem-1" });
    expect(body).toMatchObject({ run_id: "run-1", modalities: ["TEXT", "IMAGE"], estimated_input_tokens: 3 });
    expect(body).not.toHaveProperty("scope");
    expect(body).not.toHaveProperty("provider_id");
    expect(body).not.toHaveProperty("context_snapshot_ref");
    expect(body).not.toHaveProperty("data_class");
    expect(draft).toMatchObject({ run_id: "run-1", status: "DRAFT", draft_version: "experience-draft.v1" });
    expect(draft.provenance).toMatchObject({ provider_id: "approved-provider", model_version: "model-v1", latency_ms: 420 });
    expect(draft.provenance.model_attempt_ref).toBeNull();
  });

  it.each([
    [503, "PROVIDER_NOT_ADMITTED", "refused"],
    [403, "SCOPE_MISMATCH", "refused"],
    [408, "TIMEOUT", "timeout"],
  ] as const)("maps HTTP %s to governed error", async (status, code, runStatus) => {
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ detail: "blocked" }), { status }));
    await expect(new HttpExperienceApiClient({ fetchImpl }).createDraft(input, "idem-1"))
      .rejects.toMatchObject({ code, status: runStatus });
  });

  it("maps a network failure to timeout without exposing provider details", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => { throw new Error("provider secret"); });
    await expect(new HttpExperienceApiClient({ fetchImpl }).createDraft(input, "idem-1"))
      .rejects.toMatchObject({ code: "TIMEOUT", status: "timeout" });
  });
});
