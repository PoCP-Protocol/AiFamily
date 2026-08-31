import { describe, expect, it, vi } from "vitest";
import { ProductStudioApiError } from "./api";
import {
  HttpProductPackageReviewApiClient,
  type ProductPackageReviewInput,
} from "./productPackageReviewApi";
import {
  sampleProductPackageReviewInput,
  sampleProductPackageReviewResponse,
} from "./productPackageReviewFixtures";

describe("HttpProductPackageReviewApiClient", () => {
  it("submits only browser-safe intent to the strict review route", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(
      JSON.stringify(sampleProductPackageReviewResponse),
      { status: 201 },
    ));
    const client = new HttpProductPackageReviewApiClient({
      baseUrl: "https://api.example.test",
      accessToken: "session-token",
      fetchImpl,
    });
    const forged = {
      ...sampleProductPackageReviewInput,
      zone: "UNIQUE",
      claim_type: "GROWTH_EFFECT",
      required_claim_refs: ["claim:forged"],
      source_provenance_ref: "browser:forged",
    } as ProductPackageReviewInput;

    const result = await client.submit(forged, "package-review:one");
    const [url, init] = fetchImpl.mock.calls[0];
    const body = JSON.parse(String(init?.body)) as Record<string, unknown>;

    expect(url).toBe("https://api.example.test/product-intelligence/product-package-review-submissions");
    expect(init?.headers).toMatchObject({
      Authorization: "Bearer session-token",
      "Idempotency-Key": "package-review:one",
      "content-type": "application/json",
    });
    expect(body).toEqual(sampleProductPackageReviewInput);
    expect(body).not.toHaveProperty("zone");
    expect(body).not.toHaveProperty("claim_type");
    expect(body).not.toHaveProperty("required_claim_refs");
    expect(body).not.toHaveProperty("source_provenance_ref");
    expect(result.draft.evidence_admissions[0].claim_type).toBe("MARKET_EXISTENCE");
  });

  it("reads an encoded immutable draft and preserves server replay state", async () => {
    const replay = { ...sampleProductPackageReviewResponse, replayed: true };
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(replay)));
    const client = new HttpProductPackageReviewApiClient({ fetchImpl });

    const result = await client.get("product-package-draft:one");

    expect(fetchImpl.mock.calls[0][0]).toBe(
      "/product-intelligence/product-package-review-submissions/product-package-draft%3Aone",
    );
    expect(fetchImpl.mock.calls[0][1]?.method).toBe("GET");
    expect(result.replayed).toBe(true);
  });

  it("rejects content drift while rereading the same immutable draft", async () => {
    const changedHash = "d".repeat(64);
    const drifted = {
      ...sampleProductPackageReviewResponse,
      etag: `"${changedHash}"`,
      draft: { ...sampleProductPackageReviewResponse.draft, content_hash: changedHash },
      review_task: {
        ...sampleProductPackageReviewResponse.review_task,
        provenance_ref: `product-package-draft:product-package-draft:one:${changedHash}`,
      },
    };
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(drifted)));
    await expect(new HttpProductPackageReviewApiClient({ fetchImpl })
      .get("product-package-draft:one", sampleProductPackageReviewResponse.draft.content_hash))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it("rejects incoherent admissions and ETags fail-closed", async () => {
    const missingAdmission = {
      ...sampleProductPackageReviewResponse,
      draft: { ...sampleProductPackageReviewResponse.draft, evidence_admissions: [] },
    };
    const badAdmission = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(missingAdmission)));
    await expect(new HttpProductPackageReviewApiClient({ fetchImpl: badAdmission })
      .submit(sampleProductPackageReviewInput, "idem"))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE" });

    const wrongEtag = { ...sampleProductPackageReviewResponse, etag: `"${"d".repeat(64)}"` };
    const badEtag = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(wrongEtag)));
    await expect(new HttpProductPackageReviewApiClient({ fetchImpl: badEtag })
      .submit(sampleProductPackageReviewInput, "idem"))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it("rejects a response that does not preserve the submitted design intent", async () => {
    const swapped = {
      ...sampleProductPackageReviewResponse,
      draft: { ...sampleProductPackageReviewResponse.draft, concept_id: "concept:other" },
    };
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(swapped), { status: 201 }));
    await expect(new HttpProductPackageReviewApiClient({ fetchImpl })
      .submit(sampleProductPackageReviewInput, "idem"))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it.each([
    ["verification_purpose", "other"],
    ["receipt_outcome", "REJECTED"],
    ["integrity_check", "FAIL"],
    ["relevance", "IRRELEVANT"],
    ["verification_policy_version", "unknown:v9"],
    ["admission_policy_version", "unknown:v9"],
  ] as const)("rejects a tampered evidence admission %s", async (field, value) => {
    const admission = { ...sampleProductPackageReviewResponse.draft.evidence_admissions[0], [field]: value };
    const tampered = {
      ...sampleProductPackageReviewResponse,
      draft: { ...sampleProductPackageReviewResponse.draft, evidence_admissions: [admission] },
    };
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(tampered), { status: 201 }));
    await expect(new HttpProductPackageReviewApiClient({ fetchImpl })
      .submit(sampleProductPackageReviewInput, "idem"))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it("rejects admissions without the minimum integrity methods", async () => {
    const admission = {
      ...sampleProductPackageReviewResponse.draft.evidence_admissions[0],
      verification_methods: ["SOURCE_OPENED"],
    };
    const tampered = {
      ...sampleProductPackageReviewResponse,
      draft: { ...sampleProductPackageReviewResponse.draft, evidence_admissions: [admission] },
    };
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(tampered), { status: 201 }));
    await expect(new HttpProductPackageReviewApiClient({ fetchImpl })
      .submit(sampleProductPackageReviewInput, "idem"))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it("rejects a different internally coherent receipt set", async () => {
    const admission = {
      ...sampleProductPackageReviewResponse.draft.evidence_admissions[0],
      receipt_id: "verification-receipt:other",
    };
    const swapped = {
      ...sampleProductPackageReviewResponse,
      draft: {
        ...sampleProductPackageReviewResponse.draft,
        evidence_refs: ["verification-receipt:other"],
        evidence_admissions: [admission],
      },
    };
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(swapped), { status: 201 }));
    await expect(new HttpProductPackageReviewApiClient({ fetchImpl })
      .submit(sampleProductPackageReviewInput, "idem"))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it("rejects evidence or draft expiry beyond the requested review window", async () => {
    const expiredEvidence = {
      ...sampleProductPackageReviewResponse,
      draft: {
        ...sampleProductPackageReviewResponse.draft,
        evidence_admissions: [{
          ...sampleProductPackageReviewResponse.draft.evidence_admissions[0],
          valid_until: "2026-09-01T17:00:00Z",
        }],
      },
    };
    const evidenceFetch = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(expiredEvidence), { status: 201 }));
    await expect(new HttpProductPackageReviewApiClient({ fetchImpl: evidenceFetch })
      .submit(sampleProductPackageReviewInput, "idem"))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE" });

    const lateExpiry = {
      ...sampleProductPackageReviewResponse,
      draft: { ...sampleProductPackageReviewResponse.draft, expires_at: "2026-09-01T19:00:00Z" },
      review_task: { ...sampleProductPackageReviewResponse.review_task, expires_at: "2026-09-01T19:00:00Z" },
    };
    const ttlFetch = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(lateExpiry), { status: 201 }));
    await expect(new HttpProductPackageReviewApiClient({ fetchImpl: ttlFetch })
      .submit(sampleProductPackageReviewInput, "idem"))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it("rejects a Human Gate task that is not bound to the frozen draft", async () => {
    const wrongTask = {
      ...sampleProductPackageReviewResponse,
      review_task: { ...sampleProductPackageReviewResponse.review_task, action_name: "OTHER_ACTION" },
    };
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(JSON.stringify(wrongTask), { status: 201 }));
    await expect(new HttpProductPackageReviewApiClient({ fetchImpl })
      .submit(sampleProductPackageReviewInput, "idem"))
      .rejects.toMatchObject({ code: "INVALID_RESPONSE" });
  });

  it.each([
    [401, "UNAUTHORIZED"],
    [403, "FORBIDDEN"],
    [404, "NOT_FOUND"],
    [409, "CONFLICT"],
    [422, "INVALID_INPUT"],
    [500, "UNAVAILABLE"],
    [502, "UNAVAILABLE"],
    [503, "UNAVAILABLE"],
    [504, "TIMEOUT"],
  ] as const)("maps HTTP %s to %s", async (status, code) => {
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(
      JSON.stringify({ detail: "PRODUCT_PACKAGE_BLOCKED" }),
      { status },
    ));
    await expect(new HttpProductPackageReviewApiClient({ fetchImpl })
      .submit(sampleProductPackageReviewInput, "idem"))
      .rejects.toMatchObject({ code, httpStatus: status });
  });

  it("requires identifiers and hides network details", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => { throw new Error("provider-secret"); });
    const client = new HttpProductPackageReviewApiClient({ fetchImpl });
    await expect(client.submit(sampleProductPackageReviewInput, " "))
      .rejects.toEqual(expect.objectContaining({ code: "INVALID_INPUT" }));
    await expect(client.get(" "))
      .rejects.toEqual(expect.objectContaining({ code: "INVALID_INPUT" }));
    await expect(client.submit(sampleProductPackageReviewInput, "idem"))
      .rejects.toEqual(expect.objectContaining({
        code: "TIMEOUT",
        message: expect.not.stringContaining("provider-secret"),
      }));
    expect(new ProductStudioApiError("CONFLICT", "x")).toBeInstanceOf(Error);
  });
});
