import { describe, expect, it, vi } from "vitest";
import { FamilyGrowthApiClient, FamilyGrowthApiError } from "./client";

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("FamilyGrowthApiClient", () => {
  it("reads assessment and growth contracts with a bearer token", async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(response({ projection_version: "UI02", availability: "READY", dimensions: [] }))
      .mockResolvedValueOnce(response({ projection_version: "UI03", availability: "READY", hypothesis: null }));
    const client = new FamilyGrowthApiClient({ baseUrl: "https://api.example", accessToken: "token-1", fetchImpl });

    await client.getAssessment("family/1");
    await client.getGrowthHypothesis("family/1");

    expect(fetchImpl).toHaveBeenNthCalledWith(
      1,
      "https://api.example/families/family%2F1/ui/02/assessment",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
    const firstHeaders = fetchImpl.mock.calls[0][1].headers as Headers;
    expect(firstHeaders.get("authorization")).toBe("Bearer token-1");
  });

  it("posts responses with an idempotency key and exposes the growth path route", async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(response({ session_id: "s-1", status: "STARTED" }))
      .mockResolvedValueOnce(response({
        family_need_id: "need-1",
        path_id: "path-1",
        run_id: "run-1",
        context_snapshot_ref: "context-1",
        decision_ref: null,
        decision_state: null,
        next_step: "先谈一次",
        path: [],
        status: "DRAFT",
        requires_human_confirmation: true,
      }));
    const client = new FamilyGrowthApiClient({ fetchImpl });

    await client.startAssessment("family-1", { subject_person_id: "child-1", tool_ref: "tool-1" }, "idem-1");
    const path = await client.getGrowthPath("family-1", "run-1");

    expect(path.next_step).toBe("先谈一次");
    expect(fetchImpl.mock.calls[0][0]).toBe("/families/family-1/assessments/sessions");
    const headers = fetchImpl.mock.calls[0][1].headers as Headers;
    expect(headers.get("Idempotency-Key")).toBe("idem-1");
    expect(fetchImpl.mock.calls[1][0]).toBe(
      "/families/family-1/experience/multimodal/runs/run-1/growth-path",
    );
  });

  it("preserves server status and detail when the route is unavailable", async () => {
    const client = new FamilyGrowthApiClient({ fetchImpl: vi.fn().mockResolvedValue(response({ detail: "not_ready" }, 503)) });
    await expect(client.getAssessment("family-1")).rejects.toEqual(
      expect.objectContaining<Partial<FamilyGrowthApiError>>({ status: 503, detail: "not_ready" }),
    );
  });

  it("uses the canonical durable vertical draft and guardian decision routes", async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce(response({
        family_need_id: "need-1", path_id: "path-1", run_id: "run-1",
        context_snapshot_ref: "context-1", status: "DRAFT", output: { understanding: "u", next_step: "n" },
        feedback_refs: [], capability_refs: [], knowledge_ref: "vertical-growth.v1", knowledge_version: "v1", lineage_ref: "l", provenance: {},
      }))
      .mockResolvedValueOnce(response({
        family_need_id: "need-1", path_id: "path-1", run_id: "run-1",
        context_snapshot_ref: "context-1", status: "DRAFT", output: { understanding: "u", next_step: "n", path: [] },
        feedback_refs: ["guardian-1"], capability_refs: [], knowledge_ref: "vertical-growth.v1", knowledge_version: "v1", lineage_ref: "l", provenance: {},
      }));
    const client = new FamilyGrowthApiClient({ fetchImpl });

    await client.createVerticalDraft("family-1", {
      family_need_id: "need-1", path_id: "path-1", run_id: "run-1", knowledge_ref: "vertical-growth.v1",
    }, "draft-1");
    await client.decideVerticalDraft("family-1", "run-1", {
      decision_ref: "guardian-1", family_need_id: "need-1", path_id: "path-1", state: "ACCEPT",
    }, "decision-1");

    expect(fetchImpl.mock.calls[0][0]).toBe("/families/family-1/growth/ai-drafts");
    expect(fetchImpl.mock.calls[1][0]).toBe("/families/family-1/growth/ai-drafts/run-1/decisions");
  });
});
