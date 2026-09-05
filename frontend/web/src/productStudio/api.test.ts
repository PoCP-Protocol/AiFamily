import { describe, expect, it, vi } from "vitest";
import {
  HttpProductStudioApiClient,
  ProductStudioApiError,
  type DemandFrameInput,
} from "./api";

const demand: DemandFrameInput = {
  statement: "家庭需要更容易开始的小行动。",
  scenario: "evening_routine",
  source_refs: ["voc:001"],
  target_segment: "家庭照护者",
  locale: "zh-CN",
  purpose: "product_discovery",
  evidence_refs: ["evidence:001"],
  assumptions: ["assumption:001"],
  unknowns: ["unknown:001"],
  next_validation: "访谈并观察七天",
  expires_at: "2099-01-01T00:00:00Z",
  provenance_ref: "model-draft:demand-001",
};

const draft = {
  draft_id: "draft-001",
  product_definition_id: null,
  demand_id: "demand-001",
  statement: demand.statement,
  version: "1.0.0",
  status: "DRAFT",
  provenance_ref: "model-draft:demand-001",
  ai_provenance: { model_ref: "model-v1", provenance_ref: "model-draft:demand-001" },
};

const competitorDraft = {
  ...draft,
  evidence_refs: ["source:001"],
  assumptions: ["页面信息仍然有效"],
  unknowns: ["实际使用效果未知"],
  next_validation: "访谈五位家长",
  expires_at: "2099-01-01T00:00:00+08:00",
  evidence_id: "competitor-evidence:001",
  competitor_ref: "competitor:001",
  claim: "可核查主张",
  source_refs: ["source:001"],
  source_type: "official_webpage",
  evidence_status: "UNKNOWN",
};

const marketInsightDraft = {
  ...draft,
  evidence_refs: ["source:001", "competitor-evidence:001"],
  assumptions: ["透明度影响采用"],
  unknowns: ["支付意愿未知"],
  next_validation: "开展概念测试",
  expires_at: "2099-01-01T00:00:00+08:00",
  insight_id: "market-insight:001",
  demand_ref: "demand-001",
  statement: "可核查市场洞察",
  source_refs: ["source:001"],
  competitor_evidence_refs: ["competitor-evidence:001"],
};

describe("HttpProductStudioApiClient", () => {
  it.each([
    ["createDemandFrame", "/demand-frames", draft],
    ["createMarketInsight", "/market-insights", marketInsightDraft],
    ["createCompetitorEvidence", "/competitor-evidence", competitorDraft],
  ] as const)("maps %s to the draft-only product factory route", async (method, suffix, responseBody) => {
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(responseBody), { status: 201 }));
    const client = new HttpProductStudioApiClient({ baseUrl: "https://api.example.test", fetchImpl });
    const result = await client[method](demand as never, "product-idem-1");
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe(`https://api.example.test/product-intelligence/product-factory${suffix}`);
    expect(init?.method).toBe("POST");
    expect(init?.headers).toMatchObject({ "content-type": "application/json", "Idempotency-Key": "product-idem-1" });
    expect(result).toMatchObject({ status: "DRAFT", provenance_ref: "model-draft:demand-001" });
    expect(result.draft_id).toBe("draft-001");
  });

  it("reads a persisted competitor evidence card with an encoded id", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(competitorDraft), { status: 200 }));
    const client = new HttpProductStudioApiClient({ baseUrl: "https://api.example.test", fetchImpl });
    const result = await client.getCompetitorEvidence("competitor-evidence:001/中文");
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("https://api.example.test/product-intelligence/product-factory/competitor-evidence/competitor-evidence%3A001%2F%E4%B8%AD%E6%96%87");
    expect(init?.method).toBe("GET");
    expect(result).toMatchObject({ evidence_id: "competitor-evidence:001", evidence_status: "UNKNOWN", status: "DRAFT" });
  });

  it("injects a bearer token without exposing it in the request body", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(competitorDraft), { status: 201 }));
    const client = new HttpProductStudioApiClient({
      fetchImpl,
      accessTokenProvider: () => "session-token",
    });
    await client.createCompetitorEvidence(demand as never, "idem-auth");
    const [, init] = fetchImpl.mock.calls[0];
    expect(init?.headers).toMatchObject({ Authorization: "Bearer session-token" });
    expect(init?.body).not.toContain("session-token");
  });

  it("preserves an existing Bearer prefix", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(competitorDraft), { status: 200 }));
    const client = new HttpProductStudioApiClient({ fetchImpl, accessToken: "Bearer existing-token" });
    await client.getCompetitorEvidence("competitor-evidence:001");
    expect(fetchImpl.mock.calls[0][1]?.headers).toMatchObject({ Authorization: "Bearer existing-token" });
  });

  it("rejects non-DRAFT or provenance-less responses fail-closed", async () => {
    const nonDraft = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ status: "PUBLISHED", provenance_ref: "x" }), { status: 200 }));
    await expect(new HttpProductStudioApiClient({ fetchImpl: nonDraft }).createDemandFrame(demand, "idem")).rejects.toMatchObject({ code: "INVALID_RESPONSE" });

    const noProvenance = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ status: "DRAFT" }), { status: 200 }));
    await expect(new HttpProductStudioApiClient({ fetchImpl: noProvenance }).createDemandFrame(demand, "idem")).rejects.toMatchObject({ code: "INVALID_RESPONSE" });

    const blankProvenance = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ status: "DRAFT", provenance_ref: "  " }), { status: 200 }));
    await expect(new HttpProductStudioApiClient({ fetchImpl: blankProvenance }).createDemandFrame(demand, "idem")).rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it("accepts nested ai_provenance when the top-level reference is omitted", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ status: "DRAFT", ai_provenance: { provenance_ref: "model-draft:nested" } }), { status: 200 }));
    const result = await new HttpProductStudioApiClient({ fetchImpl }).createDemandFrame(demand, "idem");
    expect(result.provenance_ref).toBe("model-draft:nested");
  });

  it("rejects malformed evidence and insight payloads fail-closed", async () => {
    const malformedEvidence = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ ...draft, evidence_status: "SCORED" }), { status: 200 }));
    await expect(new HttpProductStudioApiClient({ fetchImpl: malformedEvidence }).getCompetitorEvidence("evidence:001"))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE" });

    const malformedInsight = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ ...marketInsightDraft, competitor_evidence_refs: [""] }), { status: 201 }));
    await expect(new HttpProductStudioApiClient({ fetchImpl: malformedInsight }).createMarketInsight(demand as never, "idem"))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it.each([
    [401, "UNAUTHORIZED"],
    [403, "FORBIDDEN"],
    [404, "NOT_FOUND"],
    [409, "CONFLICT"],
    [422, "INVALID_INPUT"],
    [503, "UNAVAILABLE"],
    [504, "TIMEOUT"],
  ] as const)("maps HTTP %s to %s", async (status, code) => {
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ detail: "blocked" }), { status }));
    await expect(new HttpProductStudioApiClient({ fetchImpl }).createDemandFrame(demand, "idem")).rejects.toMatchObject({ code, httpStatus: status });
  });

  it("fails closed on missing idempotency and network errors", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => { throw new Error("provider secret"); });
    await expect(new HttpProductStudioApiClient({ fetchImpl }).createDemandFrame(demand, "  ")).rejects.toMatchObject({ code: "INVALID_INPUT" });
    await expect(new HttpProductStudioApiClient({ fetchImpl }).createDemandFrame(demand, "idem")).rejects.toMatchObject({ code: "TIMEOUT" });
  });

  it("fails closed when competitor evidence read-back has no id", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(competitorDraft), { status: 200 }));
    const client = new HttpProductStudioApiClient({ fetchImpl });
    await expect(client.getCompetitorEvidence("  ")).rejects.toMatchObject({ code: "INVALID_INPUT" });
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});
