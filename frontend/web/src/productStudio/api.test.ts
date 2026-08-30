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
  demand_id: "demand-001",
  statement: demand.statement,
  version: "1.0.0",
  status: "DRAFT",
  provenance_ref: "model-draft:demand-001",
  ai_provenance: { model_ref: "model-v1", provenance_ref: "model-draft:demand-001" },
};

describe("HttpProductStudioApiClient", () => {
  it.each([
    ["createDemandFrame", "/demand-frames"],
    ["createMarketInsight", "/market-insights"],
    ["createCompetitorEvidence", "/competitor-evidence"],
    ["createProductPackage", "/product-packages"],
  ] as const)("maps %s to the draft-only product factory route", async (method, suffix) => {
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(draft), { status: 201 }));
    const client = new HttpProductStudioApiClient({ baseUrl: "https://api.example.test", fetchImpl });
    const result = await client[method](demand as never, "product-idem-1");
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe(`https://api.example.test/product-intelligence/product-factory${suffix}`);
    expect(init?.method).toBe("POST");
    expect(init?.headers).toMatchObject({ "content-type": "application/json", "Idempotency-Key": "product-idem-1" });
    expect(result).toMatchObject({ status: "DRAFT", provenance_ref: "model-draft:demand-001" });
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
});
