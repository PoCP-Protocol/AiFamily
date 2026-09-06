import { describe, expect, it, vi } from "vitest";

import { FamilyApiClient } from "../lib/family/family-api-client";

describe("dev account session idempotency", () => {
  it("sends a stable key and does not regress to the server's missing-header 400", async () => {
    const fetcher = vi.fn(
      async (_input: RequestInfo | URL, init?: RequestInit) => {
        const key = new Headers(init?.headers).get("idempotency-key");
        if (!key) {
          return new Response(
            JSON.stringify({ detail: "idempotency-key header is required" }),
            { status: 400 },
          );
        }
        return new Response(
          JSON.stringify({
            token: "session-token",
            expires_at: "2099-01-01T00:00:00+00:00",
            account_id: "account-1",
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      },
    ) as unknown as typeof fetch;
    const client = new FamilyApiClient("https://family.example", fetcher);

    await expect(
      client.issueDevAccountSession("account-1:family-1"),
    ).resolves.toMatchObject({ token: "session-token" });

    const [, request] = vi.mocked(fetcher).mock.calls[0];
    expect(request?.headers).toMatchObject({
      "idempotency-key": "account-session:account-1:family-1",
    });
    expect(JSON.parse(request?.body as string)).toEqual({
      external_ref: "account-1:family-1",
    });
  });

  it("reuses the same key for repeated external refs and replays the same response", async () => {
    const responses = new Map<string, Response>();
    const fetcher = vi.fn(
      async (_input: RequestInfo | URL, init?: RequestInit) => {
        const key = new Headers(init?.headers).get("idempotency-key")!;
        const existing = responses.get(key);
        if (existing) return existing.clone();
        const response = new Response(
          JSON.stringify({
            token: "first-session",
            expires_at: "2099-01-01T00:00:00+00:00",
            account_id: "account-1",
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
        responses.set(key, response.clone());
        return response;
      },
    ) as unknown as typeof fetch;
    const client = new FamilyApiClient("https://family.example", fetcher);

    const first = await client.issueDevAccountSession("account-1:family-1");
    const replay = await client.issueDevAccountSession("account-1:family-1");

    expect(replay).toEqual(first);
    expect(fetcher).toHaveBeenCalledTimes(2);
    const firstKey = new Headers(
      vi.mocked(fetcher).mock.calls[0][1]?.headers,
    ).get("idempotency-key");
    const replayKey = new Headers(
      vi.mocked(fetcher).mock.calls[1][1]?.headers,
    ).get("idempotency-key");
    expect(replayKey).toBe(firstKey);
  });
});
