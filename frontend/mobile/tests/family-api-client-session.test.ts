import { describe, expect, it, vi } from "vitest";

import { FamilyApiClient } from "../lib/family/family-api-client";

describe("Family API dev session request", () => {
  it("sends a stable idempotency key without a tenant header", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({
      token: "token-1",
      expires_at: "2099-01-01T00:00:00Z",
      account_id: "account-1",
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })) as unknown as typeof fetch;
    const client = new FamilyApiClient("https://family.example", fetcher);
    const externalRef = "account-1:family-1";

    await client.issueDevAccountSession(externalRef);
    await client.issueDevAccountSession(externalRef);

    expect(fetcher).toHaveBeenCalledTimes(2);
    const requests = vi.mocked(fetcher).mock.calls.map(([, request]) => request);
    for (const request of requests) {
      expect(request?.method).toBe("POST");
      expect(request?.credentials).toBe("omit");
      expect(request?.headers).toMatchObject({
        "idempotency-key": "family-mobile-auth-session:account-1%3Afamily-1",
      });
      expect(request?.headers).not.toHaveProperty("tenant");
      expect(request?.headers).not.toHaveProperty("tenant-id");
      expect(request?.headers).not.toHaveProperty("x-tenant-id");
      expect(JSON.parse(request?.body as string)).toEqual({ external_ref: externalRef });
    }

    expect(requests[0]?.headers).toEqual(requests[1]?.headers);
  });

  it("keeps the mobile session-to-UI-03 request sequence family-scoped", async () => {
    // DEMO_ONLY: mocked HTTP responses verify client request wiring only, not a real API or PG run.
    const responses = [
      { token: "token-1", expires_at: "2099-01-01T00:00:00Z", account_id: "account-1" },
      { account_id: "account-1", contexts: [{ type: "FAMILY", tenant_id: "tenant-1", family_id: "family-1", person_id: "person-1", membership_id: "membership-1", role: "GUARDIAN" }] },
      { entry_state: "READY", availability: "AVAILABLE" },
      { projection_version: "UI03_GROWTH_HYPOTHESIS_V1", availability: "EMPTY", hypothesis: null },
    ];
    let responseIndex = 0;
    const fetcher = vi.fn(async () => new Response(JSON.stringify(responses[responseIndex++]), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })) as unknown as typeof fetch;
    const client = new FamilyApiClient("https://family.example", fetcher);

    const session = await client.issueDevAccountSession("account-1:family-1");
    await client.getContexts(session.token);
    await client.getFamilyAssessment(session.token, "family-1");
    await client.getGrowthHypothesis(session.token, "family-1");

    expect(vi.mocked(fetcher).mock.calls.map(([url]) => url)).toEqual([
      "https://family.example/auth/account-session",
      "https://family.example/auth/contexts",
      "https://family.example/families/family-1/ui/02/assessment",
      "https://family.example/families/family-1/ui/03/growth-hypothesis",
    ]);
    const requests = vi.mocked(fetcher).mock.calls.map(([, request]) => request);
    expect(requests[0]?.headers).toMatchObject({
      "idempotency-key": "family-mobile-auth-session:account-1%3Afamily-1",
    });
    for (const request of requests.slice(1)) {
      expect(request?.headers).toMatchObject({ Authorization: "Bearer token-1" });
    }
    for (const request of requests) {
      expect(request?.headers).not.toHaveProperty("tenant");
      expect(request?.headers).not.toHaveProperty("tenant-id");
      expect(request?.headers).not.toHaveProperty("x-tenant-id");
    }
  });
});
