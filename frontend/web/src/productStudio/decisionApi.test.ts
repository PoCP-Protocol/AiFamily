import { describe, expect, it, vi } from "vitest";
import {
  HttpProductDecisionApiClient,
  ZONE_DIMENSIONS,
  type CandidateReference,
} from "./decisionApi";

const references: CandidateReference[] = [
  { conceptId: "concept:one", assessmentId: "assessment:one" },
  { conceptId: "concept:two", assessmentId: "assessment:two" },
];

const chain = (id: string, title = id, overrides: Record<string, unknown> = {}) => ({
  product_concept: { id, version: 1, strategy_id: `strategy:${id}`, title, description: `${title} 描述`, status: "DRAFT" },
  growth_strategy: { id: `strategy:${id}`, problem_id: `problem:${id}`, statement: "从催促转为共同规划", status: "DRAFT", version: 1 },
  growth_problem: { id: `problem:${id}`, opportunity_id: "opportunity:decision-room", symptom: "高频催促冲突", evidence_refs: ["evidence:problem"], status: "ACTIVE", version: 1 },
  opportunity: { id: "opportunity:decision-room", insight_id: "insight:decision-room", statement: "需要可逐步减少催促的服务", evidence_refs: ["evidence:opportunity"], status: "WATCH", version: 2 },
  customer_insight: { id: "insight:decision-room", signal_id: "signal:decision-room", statement: "家长希望降低冲突", evidence_refs: ["evidence:insight"], status: "ACTIVE", version: 1 },
  market_signal: { id: "signal:decision-room", raw_text: "多次访谈提到催促冲突", source_ref: "research:interview", evidence_refs: ["evidence:signal"], status: "ACTIVE", version: 1 },
  growth_hypotheses: [],
  ...overrides,
});

const assessment = (id: string, conceptId: string, overrides: Record<string, unknown> = {}) => ({
  id,
  version: 1,
  subject_type: "PRODUCT_CONCEPT",
  subject_ref: conceptId,
  zone_policy_version_id: "zone-policy:v1",
  status: "SCORED",
  recommended_zone: "ADVANTAGE",
  approved_zone: null,
  override_reason: null,
  reviewed_by: null,
  reviewed_at: null,
  review_reason: null,
  differentiation_index: 62,
  defensibility_index: 58,
  dimension_assessments: ZONE_DIMENSIONS.map((dimension, index) => ({
    dimension,
    score: 50 + index,
    rationale: `${dimension} 有可核查依据`,
    evidence_refs: [`evidence:${dimension}`],
    evidence_strength: 0.7,
  })),
  ...overrides,
});

function responseForUrl(url: string): unknown {
  if (url.includes("concept%3Aone/chain")) return chain("concept:one", "候选一");
  if (url.includes("concept%3Atwo/chain")) return chain("concept:two", "候选二");
  if (url.includes("assessment%3Aone")) return assessment("assessment:one", "concept:one");
  if (url.includes("assessment%3Atwo")) return assessment("assessment:two", "concept:two");
  throw new Error(`unexpected url: ${url}`);
}

describe("HttpProductDecisionApiClient", () => {
  it("loads chain and assessment pairs in parallel while preserving input order", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => new Response(JSON.stringify(responseForUrl(String(input))), { status: 200 }));
    const client = new HttpProductDecisionApiClient({ baseUrl: "https://api.example.test", fetchImpl });
    const result = await client.loadCandidates(references);

    expect(fetchImpl).toHaveBeenCalledTimes(4);
    expect(result.map(({ concept }) => concept.id)).toEqual(["concept:one", "concept:two"]);
    expect(result[0].assessment.dimension_assessments).toHaveLength(6);
    expect(result[0].lineage.opportunity?.status).toBe("WATCH");
    expect(result[0].lineage.review_state).toBe("NEEDS_HUMAN_DECISION");
  });

  it("injects Bearer auth into every read without adding request bodies", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => new Response(JSON.stringify(responseForUrl(String(input))), { status: 200 }));
    const client = new HttpProductDecisionApiClient({ fetchImpl, accessTokenProvider: () => "session-token" });
    await client.loadCandidates(references);
    for (const [, init] of fetchImpl.mock.calls) {
      expect(init).toMatchObject({ method: "GET", headers: { Authorization: "Bearer session-token" } });
      expect(init?.body).toBeUndefined();
    }
  });

  it.each([
    [[references[0]], "候选数量必须为 2–5 个"],
    [[...references, ...references, references[0], references[1]], "候选数量必须为 2–5 个"],
    [[references[0], references[0]], "不得重复"],
    [[references[0], { conceptId: "", assessmentId: "assessment:two" }], "必须提供"],
  ] as const)("rejects invalid candidate references before fetch", async (invalid, message) => {
    const fetchImpl = vi.fn<typeof fetch>();
    await expect(new HttpProductDecisionApiClient({ fetchImpl }).loadCandidates([...invalid]))
      .rejects.toMatchObject({ code: "INVALID_INPUT", message: expect.stringContaining(message) });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("fails closed when assessment and concept ids do not match", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      const body = url.includes("/chain")
        ? chain(url.includes("one") ? "concept:one" : "concept:two")
        : assessment(
          url.includes("one") ? "assessment:one" : "assessment:two",
          "concept:wrong",
        );
      return new Response(JSON.stringify(body), { status: 200 });
    });
    await expect(new HttpProductDecisionApiClient({ fetchImpl }).loadCandidates(references))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE", message: expect.stringContaining("不匹配") });
  });

  it("fails closed when the Opportunity ancestry conflicts", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      const isOne = decodeURIComponent(url).includes(":one");
      const conceptId = isOne ? "concept:one" : "concept:two";
      const body = url.includes("/chain")
        ? chain(conceptId, conceptId, isOne ? { growth_problem: { id: `problem:${conceptId}`, opportunity_id: "opportunity:wrong", symptom: "冲突", evidence_refs: [], status: "ACTIVE", version: 1 } } : {})
        : assessment(isOne ? "assessment:one" : "assessment:two", conceptId);
      return new Response(JSON.stringify(body), { status: 200 });
    });
    await expect(new HttpProductDecisionApiClient({ fetchImpl }).loadCandidates(references))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE", message: expect.stringContaining("不匹配") });
  });

  it("fails closed when candidates are from different Opportunity scopes", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      const decoded = decodeURIComponent(url);
      const isOne = decoded.includes(":one");
      const conceptId = isOne ? "concept:one" : "concept:two";
      const body = url.includes("/chain")
        ? chain(conceptId, conceptId, isOne ? {} : {
          growth_problem: { id: `problem:${conceptId}`, opportunity_id: "opportunity:other", symptom: "冲突", evidence_refs: [], status: "ACTIVE", version: 1 },
          opportunity: { id: "opportunity:other", insight_id: "insight:other", statement: "另一机会", evidence_refs: [], status: "WATCH", version: 1 },
          customer_insight: { id: "insight:other", signal_id: "signal:other", statement: "另一洞察", evidence_refs: [], status: "ACTIVE", version: 1 },
          market_signal: { id: "signal:other", raw_text: "另一信号", source_ref: null, evidence_refs: [], status: "ACTIVE", version: 1 },
        })
        : assessment(isOne ? "assessment:one" : "assessment:two", conceptId);
      return new Response(JSON.stringify(body), { status: 200 });
    });
    await expect(new HttpProductDecisionApiClient({ fetchImpl }).loadCandidates(references))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE", message: expect.stringContaining("同一个 Opportunity") });
  });

  it("fails closed when candidates use different versions of the same Opportunity", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      const decoded = decodeURIComponent(url);
      const isOne = decoded.includes(":one");
      const conceptId = isOne ? "concept:one" : "concept:two";
      const body = url.includes("/chain")
        ? chain(conceptId, conceptId, isOne ? {} : { opportunity: { id: "opportunity:decision-room", insight_id: "insight:decision-room", statement: "同一机会的新版本", evidence_refs: [], status: "WATCH", version: 3 } })
        : assessment(isOne ? "assessment:one" : "assessment:two", conceptId);
      return new Response(JSON.stringify(body), { status: 200 });
    });
    await expect(new HttpProductDecisionApiClient({ fetchImpl }).loadCandidates(references))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE", message: expect.stringContaining("同一个 Opportunity") });
  });

  it("fails closed when candidates use different zone policy versions", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      const decoded = decodeURIComponent(url);
      const isOne = decoded.includes(":one");
      const conceptId = isOne ? "concept:one" : "concept:two";
      const body = url.includes("/chain")
        ? chain(conceptId)
        : assessment(isOne ? "assessment:one" : "assessment:two", conceptId, isOne ? {} : { zone_policy_version_id: "zone-policy:v2" });
      return new Response(JSON.stringify(body), { status: 200 });
    });
    await expect(new HttpProductDecisionApiClient({ fetchImpl }).loadCandidates(references))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE", message: expect.stringContaining("策略版本") });
  });

  it("allows an explicit incomplete upstream tail without inventing an Opportunity", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      const isOne = decodeURIComponent(url).includes(":one");
      const conceptId = isOne ? "concept:one" : "concept:two";
      const body = url.includes("/chain")
        ? chain(conceptId, conceptId, { growth_problem: { id: `problem:${conceptId}`, opportunity_id: null, symptom: "冲突", evidence_refs: [], status: "ACTIVE", version: 1 }, opportunity: null, customer_insight: null, market_signal: null })
        : assessment(isOne ? "assessment:one" : "assessment:two", conceptId);
      return new Response(JSON.stringify(body), { status: 200 });
    });
    const result = await new HttpProductDecisionApiClient({ fetchImpl }).loadCandidates(references);
    expect(result[0].lineage.completeness).toBe("INCOMPLETE_UPSTREAM");
    expect(result[0].lineage.opportunity).toBeNull();
  });

  it("rejects missing nullable chain keys instead of treating them as explicit null", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      const decoded = decodeURIComponent(url);
      const isOne = decoded.includes(":one");
      const conceptId = isOne ? "concept:one" : "concept:two";
      const incomplete = chain(conceptId, conceptId, { growth_problem: { id: `problem:${conceptId}`, opportunity_id: null, symptom: "冲突", evidence_refs: [], status: "ACTIVE", version: 1 } });
      if (url.includes("/chain")) {
        delete (incomplete as Record<string, unknown>).opportunity;
        return new Response(JSON.stringify(incomplete), { status: 200 });
      }
      return new Response(JSON.stringify(assessment(isOne ? "assessment:one" : "assessment:two", conceptId)), { status: 200 });
    });
    await expect(new HttpProductDecisionApiClient({ fetchImpl }).loadCandidates(references))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE", message: expect.stringContaining("Opportunity 字段缺失") });
  });

  it("fails closed when an approved assessment has no approved zone", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      const isOne = url.includes("one");
      const body = url.includes("/chain")
        ? chain(isOne ? "concept:one" : "concept:two")
        : assessment(
          isOne ? "assessment:one" : "assessment:two",
          isOne ? "concept:one" : "concept:two",
          isOne ? { status: "APPROVED", approved_zone: null } : {},
        );
      return new Response(JSON.stringify(body), { status: 200 });
    });
    await expect(new HttpProductDecisionApiClient({ fetchImpl }).loadCandidates(references))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE", message: expect.stringContaining("approved_zone") });
  });

  it("fails closed when a completed assessment lacks human review lineage", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      const decoded = decodeURIComponent(url);
      const isOne = decoded.includes(":one");
      const conceptId = isOne ? "concept:one" : "concept:two";
      const body = url.includes("/chain")
        ? chain(conceptId)
        : assessment(
          isOne ? "assessment:one" : "assessment:two",
          conceptId,
          isOne ? { status: "APPROVED", approved_zone: "ADVANTAGE" } : {},
        );
      return new Response(JSON.stringify(body), { status: 200 });
    });
    await expect(new HttpProductDecisionApiClient({ fetchImpl }).loadCandidates(references))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE", message: expect.stringContaining("reviewer、时间或理由") });
  });

  it.each([
    [ZONE_DIMENSIONS.slice(0, 5).map((dimension) => ({ dimension, score: 50, rationale: "依据", evidence_refs: ["e:1"], evidence_strength: 0.5 })), "完整六维"],
    [ZONE_DIMENSIONS.map((dimension) => ({ dimension, score: 50, rationale: "依据", evidence_refs: dimension === "network_effect" ? [] : ["e:1"], evidence_strength: 0.5 })), "缺少有效 FACT_REF evidence_refs"],
  ] as const)("fails closed for incomplete dimension evidence", async (dimensionAssessments, message) => {
    const fetchImpl = vi.fn<typeof fetch>(async (input) => {
      const url = String(input);
      const isOne = url.includes("one");
      const body = url.includes("/chain")
        ? chain(isOne ? "concept:one" : "concept:two")
        : assessment(
          isOne ? "assessment:one" : "assessment:two",
          isOne ? "concept:one" : "concept:two",
          isOne ? { dimension_assessments: dimensionAssessments } : {},
        );
      return new Response(JSON.stringify(body), { status: 200 });
    });
    await expect(new HttpProductDecisionApiClient({ fetchImpl }).loadCandidates(references))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE", message: expect.stringContaining(message) });
  });

  it.each([
    [401, "UNAUTHORIZED"],
    [403, "FORBIDDEN"],
    [404, "NOT_FOUND"],
    [503, "UNAVAILABLE"],
    [504, "TIMEOUT"],
  ] as const)("maps HTTP %s to %s", async (status, code) => {
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(null, { status }));
    await expect(new HttpProductDecisionApiClient({ fetchImpl }).loadCandidates(references))
      .rejects.toMatchObject({ code, httpStatus: status });
  });

  it("maps transport failures to a non-sensitive timeout", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => { throw new Error("provider secret"); });
    await expect(new HttpProductDecisionApiClient({ fetchImpl }).loadCandidates(references))
      .rejects.toMatchObject({ code: "TIMEOUT", message: expect.not.stringContaining("secret") });
  });
});
