import { describe, expect, it, vi } from "vitest";

import { FamilyApiClient } from "../lib/family/family-api-client";

describe("AI experience feedback client", () => {
  it("marks a notification read with an idempotency key", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({
          notification_id: "achievement-notification:a/1",
          achievement_id: "a-1",
          status: "READ",
          read_at: "2026-08-30T11:00:00Z",
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );
    const client = new FamilyApiClient(
      "https://api.example.test",
      fetcher as unknown as typeof fetch,
    );

    await client.markFamilyAchievementNotificationRead(
      "token-1",
      "family-1",
      "achievement-notification:a/1",
      "idem-read-1",
    );

    expect(fetcher).toHaveBeenCalledWith(
      "https://api.example.test/families/family-1/experience/notifications/achievement-notification%3Aa%2F1/read",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({
          Authorization: "Bearer token-1",
          "idempotency-key": "idem-read-1",
          "x-source": "family-ai-mobile",
        }),
      }),
    );
  });
});
