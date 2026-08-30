import { describe, expect, it } from "vitest";

import {
  CAPABILITY_IDS,
  PLATFORM_ADAPTER_PROFILES,
  createAndroidCapabilityAdapters,
  createCapabilityRegistry,
  createPlatformCapabilityRegistry,
  createSyntheticCapabilityAdapters,
  type CapabilityRuntimeContext,
  type PlatformId,
} from "../lib/platform-capabilities";

const context = (platform: PlatformId, environment: CapabilityRuntimeContext["environment"] = "TEST"): CapabilityRuntimeContext => ({
  platform,
  environment,
  locale: "zh-CN",
  tenantScope: "synthetic-test-tenant",
});

describe("cross-platform capability contracts", () => {
  it("registers the same six business-neutral capabilities for every target platform", () => {
    for (const platform of ["ANDROID", "IOS", "HARMONYOS", "MINI_PROGRAM"] as const) {
      const registry = createPlatformCapabilityRegistry(context(platform), { synthetic: true });
      expect(registry.context.platform).toBe(platform);
      expect(registry.descriptors().map((item) => item.id)).toEqual([...CAPABILITY_IDS]);
      expect(registry.descriptors().every((item) => item.platform === platform && item.synthetic)).toBe(true);
    }
  });

  it("defaults to an explicit unavailable adapter instead of pretending production support exists", async () => {
    const registry = createPlatformCapabilityRegistry(context("IOS", "PROD"));
    expect(registry.descriptors().every((item) => item.state === "UNAVAILABLE" && !item.synthetic)).toBe(true);
    const result = await registry.get("MEDIA_CAPTURE").status();
    expect(result.state).toBe("UNAVAILABLE");
    expect(result.error?.code).toBe("CAPABILITY_UNAVAILABLE");
    expect(result.fallback).toContain("稍后");
  });

  it("keeps permission denied, low bandwidth, and fallback states visible to consumers", async () => {
    const adapters = createSyntheticCapabilityAdapters({
      context: context("ANDROID"),
      synthetic: true,
      deniedCapabilities: ["MEDIA_CAPTURE"],
      lowBandwidth: true,
      fallbackCapabilities: ["SHARING"],
    });
    const registry = createCapabilityRegistry(context("ANDROID"), adapters);
    expect((await registry.get("MEDIA_CAPTURE").status()).state).toBe("PERMISSION_DENIED");
    expect((await registry.get("MEDIA_CAPTURE").capture({ kind: "VOICE", consentRef: "consent-1", contentLocale: "zh-CN" })).state).toBe("PERMISSION_DENIED");
    expect((await registry.get("MEDIA_PLAYBACK").status()).state).toBe("LOW_BANDWIDTH");
    expect((await registry.get("MEDIA_PLAYBACK").play({ mediaRef: "media-1", kind: "VOICE" })).state).toBe("LOW_BANDWIDTH");
    expect((await registry.get("SHARING").status()).state).toBe("FALLBACK");
    const share = await registry.get("SHARING").share({ shareRef: "share-1", text: "synthetic", contentLocale: "zh-CN" });
    expect(share.state).toBe("FALLBACK");
    expect(share.value?.externalEffect).toBe(false);
  });

  it("supports synthetic media, notification, payment and storage flows without external effects", async () => {
    const registry = createPlatformCapabilityRegistry(context("MINI_PROGRAM"), { synthetic: true });
    const permission = await registry.get("MEDIA_CAPTURE").requestPermission("VOICE", "consent-voice");
    expect(permission.value?.permission).toBe("GRANTED");
    const capture = await registry.get("MEDIA_CAPTURE").capture({ kind: "VOICE", consentRef: "consent-voice", contentLocale: "zh-CN" });
    expect(capture.value).toMatchObject({ synthetic: true, visibility: "FAMILY_PRIVATE" });
    const playback = await registry.get("MEDIA_PLAYBACK").play({ mediaRef: capture.value?.mediaRef ?? "media-1", kind: "VOICE" });
    expect(playback.value?.state).toBe("PLAYING");

    const notification = await registry.get("NOTIFICATIONS").schedule({ notificationRef: "notice-1", title: "synthetic", body: "synthetic", locale: "zh-CN" });
    expect(notification.value).toMatchObject({ scheduled: true, externalEffect: false, synthetic: true });
    const cancelled = await registry.get("NOTIFICATIONS").cancel("notice-1");
    expect(cancelled.value?.cancelled).toBe(true);

    const payment = await registry.get("PAYMENTS").prepare({ intentRef: "intent-1", productRef: "PRODUCT_SYNTHETIC", currency: "CNY", amountMinor: 0, consentRef: "consent-pay", idempotencyKey: "idem-1" });
    expect(payment.value).toMatchObject({ status: "PREPARED", externalEffect: false, synthetic: true });
    const confirmation = await registry.get("PAYMENTS").confirm({ intentRef: "intent-1", hostConfirmationToken: "host-token" });
    expect(confirmation.state).toBe("FALLBACK");
    expect(confirmation.value?.externalEffect).toBe(false);

    const stored = await registry.get("STORAGE").set("family.need.draft", "synthetic");
    expect(stored.value?.persisted).toBe(true);
    expect((await registry.get("STORAGE").get("family.need.draft")).value?.value).toBe("synthetic");
    expect((await registry.get("STORAGE").remove("family.need.draft")).value?.removed).toBe(true);
  });

  it("keeps platform differences in adapter profiles, not in capability consumers", () => {
    expect(Object.keys(PLATFORM_ADAPTER_PROFILES)).toEqual(["ANDROID", "IOS", "HARMONYOS", "MINI_PROGRAM"]);
    expect(PLATFORM_ADAPTER_PROFILES.ANDROID.storageBackend).toBe("SECURE_STORE");
    expect(PLATFORM_ADAPTER_PROFILES.IOS.storageBackend).toBe("KEYCHAIN");
    expect(PLATFORM_ADAPTER_PROFILES.HARMONYOS.shareTarget).toBe("HOST_BRIDGE");
    expect(PLATFORM_ADAPTER_PROFILES.MINI_PROGRAM.paymentHost).toBe("MINI_PROGRAM_HOST");
    const android = createAndroidCapabilityAdapters({ synthetic: true, context: { environment: "TEST", locale: "zh-CN" } });
    expect(android.storage.descriptor.platform).toBe("ANDROID");
  });
});
