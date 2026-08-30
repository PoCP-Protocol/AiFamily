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
  it("injects bearer/session/locale context without trusting tenant fields", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(responseBody), { status: 200 }));
    const client = new HttpExperienceApiClient({
      baseUrl: "https://api.example.test",
      accessToken: "session-token",
      sessionId: "session-1",
      locale: "en-US",
      fetchImpl,
    });

    await client.createDraft(
      { ...input, scope: { ...input.scope, locale: "fr-FR" } },
      "idem-context",
    );

    const [, init] = fetchImpl.mock.calls[0];
    const headers = init?.headers as Record<string, string>;
    const body = JSON.parse(String(init?.body));
    expect(headers).toMatchObject({
      Authorization: "Bearer session-token",
      "X-Session-Id": "session-1",
      "X-User-Locale": "fr-FR",
    });
    expect(headers).not.toHaveProperty("X-Tenant-Id");
    expect(headers).not.toHaveProperty("X-Family-Id");
    expect(body).toMatchObject({ session_id: "session-1" });
    expect(body).not.toHaveProperty("tenant_id");
    expect(body).not.toHaveProperty("family_id");
    expect(body).not.toHaveProperty("scope");
  });

  it("sends only the backend generation body and maps a DRAFT response", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(responseBody), { status: 200 }));
    const client = new HttpExperienceApiClient({ baseUrl: "https://api.example.test", fetchImpl });
    const draft = await client.createDraft(input, "idem-1");
    const [url, init] = fetchImpl.mock.calls[0];
    const body = JSON.parse(String(init?.body));

    expect(url).toBe("https://api.example.test/families/family-1/experience/multimodal/drafts");
    expect(init?.headers).toMatchObject({ "content-type": "application/json", "Idempotency-Key": "idem-1" });
    expect(body).toMatchObject({ run_id: "run-1", modalities: ["TEXT", "IMAGE"], estimated_input_tokens: 3 });
    expect(body).not.toHaveProperty("scope");
    expect(body).not.toHaveProperty("provider_id");
    expect(body).not.toHaveProperty("context_snapshot_ref");
    expect(body).not.toHaveProperty("data_class");
    expect(draft).toMatchObject({ run_id: "run-1", status: "DRAFT", draft_version: "experience-draft.v1" });
    expect(draft.media_inputs).toEqual(input.media_inputs);
    expect(draft.provenance).toMatchObject({ provider_id: "approved-provider", model_version: "model-v1", latency_ms: 420 });
    expect(draft.provenance.model_attempt_ref).toBeNull();
  });

  it.each([
    [401, "authentication_required", "UNAUTHENTICATED", "refused"],
    [403, "family_access_denied", "SCOPE_MISMATCH", "refused"],
    [403, "TENANT_SCOPE_UNAVAILABLE", "SCOPE_MISMATCH", "refused"],
    [403, "CONSENT_REQUIRED", "CONSENT_REQUIRED", "refused"],
    [503, "blocked", "PROVIDER_NOT_ADMITTED", "refused"],
    [408, "blocked", "TIMEOUT", "timeout"],
  ] as const)("maps HTTP %s %s to governed error", async (status, detail, code, runStatus) => {
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ detail }), { status }));
    await expect(new HttpExperienceApiClient({ fetchImpl }).createDraft(input, "idem-1"))
      .rejects.toMatchObject({ code, status: runStatus });
  });

  it("maps a network failure to timeout without exposing provider details", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => { throw new Error("provider secret"); });
    await expect(new HttpExperienceApiClient({ fetchImpl }).createDraft(input, "idem-1"))
      .rejects.toMatchObject({ code: "TIMEOUT", status: "timeout" });
  });

  it("uses the run interaction routes and maps receipts/replay without provider calls", async () => {
    const interaction = (status = "recorded") => ({
      run_id: "run-1",
      status,
      interaction_ref: `event:${status}`,
      idempotency_replayed: status === "replayed",
    });
    const fetchImpl = vi.fn<typeof fetch>(async (url, init) => {
      const path = String(url);
      if (path.endsWith("/drafts")) return new Response(JSON.stringify(responseBody), { status: 200 });
      if (path.endsWith("/decisions")) return new Response(JSON.stringify(interaction()), { status: 200 });
      if (path.endsWith("/feedback")) return new Response(JSON.stringify(interaction("replayed")), { status: 200 });
      if (path.endsWith("/human-review")) return new Response(JSON.stringify(interaction()), { status: 200 });
      if (path.endsWith("/runs/run-1") && init?.method === "DELETE") return new Response(JSON.stringify({ ...interaction(), status: "deleted" }), { status: 200 });
      return new Response(JSON.stringify({
        run_id: "run-1", status: "DRAFT", state: "SUCCEEDED", event_sequence: 2,
        deletion_state: "active", draft_payload: { understanding: "draft" }, artifact_refs: [],
        entries: [{ event_id: "event:feedback", interaction_type: "feedback", sequence: 2, payload: { signal: "helpful" }, occurred_at: "2026-08-30T00:00:00Z" }],
      }), { status: 200 });
    });
    const client = new HttpExperienceApiClient({ baseUrl: "https://api.example.test", fetchImpl });
    await client.createDraft(input, "idem-create");

    const decision = await client.decide({ run_id: "run-1", decision: "confirm" }, "idem-decision");
    expect(decision).toMatchObject({ status: "recorded", interaction_ref: "event:recorded", idempotency_replayed: false });
    const feedback = await client.submitFeedback({ run_id: "run-1", signal: "helpful", event_refs: ["event:real"] }, "idem-feedback");
    expect(feedback).toMatchObject({ status: "replayed", recorded: false, idempotency_replayed: true });
    await client.requestHuman({ run_id: "run-1", reason: "需要人工" }, "idem-human");
    const deleted = await client.deleteRun("run-1", "idem-delete");
    expect(deleted.status).toBe("deleted");
    const replay = await client.replayRun("run-1");
    expect(replay).toMatchObject({ status: "DRAFT", state: "SUCCEEDED", event_sequence: 2 });
    expect(replay.entries[0]).toMatchObject({ label: "feedback", event_id: "event:feedback", sequence: 2 });

    const calls = fetchImpl.mock.calls;
    expect(String(calls[1][0])).toContain("/runs/run-1/decisions");
    expect(calls[1][1]?.headers).toMatchObject({ "Idempotency-Key": "idem-decision" });
    expect(String(calls[2][0])).toContain("/runs/run-1/feedback");
    expect(calls[2][1]?.headers).toMatchObject({ "Idempotency-Key": "idem-feedback" });
    expect(calls[2][1]?.body).toContain("real_event_refs");
    expect(String(calls[3][0])).toContain("/runs/run-1/human-review");
    expect(calls[3][1]?.headers).toMatchObject({ "Idempotency-Key": "idem-human" });
    expect(String(calls[4][0])).toContain("/runs/run-1");
    expect(calls[4][1]?.headers).toMatchObject({ "Idempotency-Key": "idem-delete" });
    expect(calls[5][1]?.method).toBe("GET");
    expect(calls[5][1]?.headers).not.toHaveProperty("Idempotency-Key");
  });

  it.each([
    [404, "RUN_NOT_FOUND", "refused"],
    [409, "CONFLICT", "refused"],
    [410, "MEDIA_DELETED", "deleted"],
    [422, "INVALID_INPUT", "refused"],
  ] as const)("maps run HTTP %s errors fail-closed", async (status, code, runStatus) => {
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ detail: "run_error" }), { status }));
    const client = new HttpExperienceApiClient({ fetchImpl, familyId: "family-1" });
    await expect(client.replayRun("run-1")).rejects.toMatchObject({ code, status: runStatus });
  });
});
