import { describe, expect, it } from "vitest";

import { FamilyApiClient, getFamilyApiRequestSnapshot, isProjectionPayloadEmpty } from "../lib/family/family-api-client";
import { deriveProjectionViewState, projectionCopyForUi } from "../lib/family/projection-state";

describe("projection loading and empty states", () => {
  it("distinguishes first load, background refresh, hard error and local fallback", () => {
    expect(deriveProjectionViewState({ phase: "loading", hasRemoteData: false, hasLocalData: false })).toBe("loading");
    expect(deriveProjectionViewState({ phase: "loading", hasRemoteData: false, hasLocalData: true })).toBe("refreshing");
    expect(deriveProjectionViewState({ phase: "error", hasRemoteData: false, hasLocalData: false })).toBe("error");
    expect(deriveProjectionViewState({ phase: "error", hasRemoteData: false, hasLocalData: true })).toBe("fallback");
  });

  it("distinguishes a remote empty result from a ready result", () => {
    expect(deriveProjectionViewState({ phase: "ready", hasRemoteData: false, hasLocalData: false })).toBe("empty");
    expect(deriveProjectionViewState({ phase: "ready", hasRemoteData: true, hasLocalData: false })).toBe("hidden");
  });

  it("recognizes null, empty arrays and common empty projection collections", () => {
    expect(isProjectionPayloadEmpty(null)).toBe(true);
    expect(isProjectionPayloadEmpty([])).toBe(true);
    expect(isProjectionPayloadEmpty({ products: [] })).toBe(true);
    expect(isProjectionPayloadEmpty({ products: [], entitlements: [] })).toBe(true);
    expect(isProjectionPayloadEmpty({ products: [{ id: "PLAN-1" }] })).toBe(false);
    expect(isProjectionPayloadEmpty({ family_id: "FAMILY-1", status: "READY" })).toBe(false);
  });

  it("uses business-specific family language for every completed page group", () => {
    expect(projectionCopyForUi("UI-03").emptyTitle).toContain("成长记录");
    expect(projectionCopyForUi("UI-14").emptyTitle).toContain("方案或权益");
    expect(projectionCopyForUi("UI-21").emptyTitle).toContain("咨询或活动");
    expect(projectionCopyForUi("UI-26").emptyTitle).toContain("家庭小记");
    expect(projectionCopyForUi("UI-32").emptyTitle).toContain("家庭成果与记录");
  });

  it("broadcasts an empty remote projection after a real request finishes", async () => {
    const client = new FamilyApiClient("https://family.test", async () => new Response(JSON.stringify({ products: [] }), { status: 200 }));
    const result = await client.getCommerceProducts<{ products: unknown[] }>("token", "family-1");

    expect(result.products).toEqual([]);
    expect(getFamilyApiRequestSnapshot()).toMatchObject({ activeCount: 0, lastResult: "empty", lastError: null });
  });

  it("broadcasts a failed remote projection without losing the error code", async () => {
    const client = new FamilyApiClient("https://family.test", async () => new Response(JSON.stringify({ message: "SERVICE_UNAVAILABLE" }), { status: 503 }));

    await expect(client.getServiceCustomerProjection("token", "family-1")).rejects.toMatchObject({ code: "SERVICE_UNAVAILABLE" });
    expect(getFamilyApiRequestSnapshot()).toMatchObject({ activeCount: 0, lastResult: "unknown", lastError: "SERVICE_UNAVAILABLE" });
  });
});
