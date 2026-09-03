import { describe, expect, it } from "vitest";

import { createPlatformCapabilityRegistry } from "../lib/platform-capabilities";
import {
  buildCapabilityHealthCards,
  healthStatusFromResult,
  isCapabilityState,
  isRetryableHealthStatus,
  mapCapabilityHealthCard,
  normalizeLocale,
} from "../lib/platform-capabilities/health-view-model";
import type { CapabilityRuntimeContext } from "../lib/platform-capabilities/contracts";
import type { CapabilityRegistry } from "../lib/platform-capabilities/registry";

const context = (platform: CapabilityRuntimeContext["platform"], locale = "zh-CN"): CapabilityRuntimeContext => ({
  platform,
  environment: "TEST",
  locale,
  tenantScope: "synthetic-health-tenant",
});

describe("platform capability health view model", () => {
  it("maps all six capability statuses for all supported platforms", async () => {
    for (const platform of ["ANDROID", "IOS", "HARMONYOS", "MINI_PROGRAM"] as const) {
      const cards = await buildCapabilityHealthCards(createPlatformCapabilityRegistry(context(platform), { synthetic: true }));
      expect(cards).toHaveLength(6);
      expect(cards.every((card) => card.platform === platform && card.status === "AVAILABLE" && card.synthetic)).toBe(true);
      expect(cards.every((card) => card.titleKey.startsWith("platform_capability.") && card.messageKey.endsWith(".AVAILABLE.message"))).toBe(true);
      expect(cards.every((card) => card.locale === "zh-CN" && card.externalEffect === false)).toBe(true);
    }
  });

  it("exposes denied, low-bandwidth and fallback states with locale-safe keys", async () => {
    const registry = createPlatformCapabilityRegistry(context("ANDROID", "fr-fr"), {
      synthetic: true,
      deniedCapabilities: ["MEDIA_CAPTURE"],
      lowBandwidth: true,
      fallbackCapabilities: ["SHARING"],
    });
    const cards = await buildCapabilityHealthCards(registry);
    const byId = new Map(cards.map((card) => [card.id, card]));
    expect(byId.get("MEDIA_CAPTURE")).toMatchObject({ status: "PERMISSION_DENIED", retryable: true, locale: "fr-FR" });
    expect(byId.get("MEDIA_PLAYBACK")).toMatchObject({ status: "LOW_BANDWIDTH", retryable: true });
    expect(byId.get("SHARING")).toMatchObject({ status: "FALLBACK", retryable: false, fallback: expect.any(String) });
    expect(byId.get("SHARING")?.messageKey).toBe("platform_capability.SHARING.FALLBACK.message");
  });

  it("turns default unconfigured adapters into a safe not-configured card", async () => {
    const cards = await buildCapabilityHealthCards(createPlatformCapabilityRegistry(context("IOS"), { synthetic: false }));
    expect(cards.every((card) => card.status === "NOT_CONFIGURED" && card.synthetic === false)).toBe(true);
    expect(cards.find((card) => card.id === "PAYMENTS")).toMatchObject({
      messageKey: "platform_capability.PAYMENTS.NOT_CONFIGURED.message",
      externalEffect: true,
      retryable: false,
      errorCode: "CAPABILITY_UNAVAILABLE",
    });
  });

  it("returns retryable not-configured cards when the health probe itself fails", async () => {
    const registry = createPlatformCapabilityRegistry(context("IOS"), { synthetic: false });
    const probeFailure = {
      ...registry,
      statusSnapshot: async () => { throw new Error("probe unavailable"); },
    } as unknown as CapabilityRegistry;
    const cards = await buildCapabilityHealthCards(probeFailure);
    expect(cards).toHaveLength(6);
    expect(cards.every((card) => card.status === "NOT_CONFIGURED" && card.retryable && card.fallback)).toBe(true);
  });

  it("preserves retryability and side-effect metadata without embedding business rules", () => {
    expect(healthStatusFromResult({ state: "UNAVAILABLE", error: { code: "CAPABILITY_UNAVAILABLE", message: "not configured", retryable: true } })).toBe("NOT_CONFIGURED");
    expect(isRetryableHealthStatus("PERMISSION_DENIED")).toBe(true);
    expect(isRetryableHealthStatus("FALLBACK")).toBe(false);
    const payment = mapCapabilityHealthCard("PAYMENTS", context("HARMONYOS"), { synthetic: false }, { state: "AVAILABLE", value: { state: "AVAILABLE", permission: "GRANTED", lowBandwidth: false, fallbackSupported: false } });
    const storage = mapCapabilityHealthCard("STORAGE", context("HARMONYOS"), { synthetic: false }, { state: "AVAILABLE", value: { state: "AVAILABLE", permission: "GRANTED", lowBandwidth: false, fallbackSupported: false } });
    expect(payment.externalEffect).toBe(true);
    expect(storage.externalEffect).toBe(false);
    expect(isCapabilityState("LOW_BANDWIDTH")).toBe(true);
    expect(isCapabilityState("BUSINESS_RULE")).toBe(false);
  });

  it("normalizes locale safely and falls back when a host supplies invalid locale text", () => {
    expect(normalizeLocale(" zh-cn ")).toBe("zh-CN");
    expect(normalizeLocale("en-us")).toBe("en-US");
    expect(normalizeLocale("")).toBe("en-US");
    expect(normalizeLocale("not-a-locale")).toBe("en-US");
  });
});
