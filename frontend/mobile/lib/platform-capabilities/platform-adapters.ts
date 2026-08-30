import { createCapabilityAdapters, type CapabilityAdapterOptions } from "./adapters";
import { createCapabilityRegistry, type CapabilityRegistry } from "./registry";
import type { CapabilityRuntimeContext, PlatformCapabilityAdapters, PlatformId } from "./contracts";

/**
 * Platform-specific details are intentionally limited to adapter metadata.
 * No family/domain decision belongs in this file.
 */
export interface PlatformAdapterProfile {
  platform: PlatformId;
  mediaCapturePermission: string;
  mediaPlaybackFallback: "TEXT" | "LOW_BITRATE";
  notificationPermission: string;
  shareTarget: "SYSTEM_SHEET" | "HOST_BRIDGE";
  paymentHost: "NATIVE_HOST" | "MINI_PROGRAM_HOST" | "UNAVAILABLE";
  storageBackend: "SECURE_STORE" | "KEYCHAIN" | "HARMONY_STORE" | "MINI_PROGRAM_STORAGE";
}

export const PLATFORM_ADAPTER_PROFILES: Record<PlatformId, PlatformAdapterProfile> = {
  ANDROID: { platform: "ANDROID", mediaCapturePermission: "android.permission.RECORD_AUDIO", mediaPlaybackFallback: "LOW_BITRATE", notificationPermission: "android.permission.POST_NOTIFICATIONS", shareTarget: "SYSTEM_SHEET", paymentHost: "NATIVE_HOST", storageBackend: "SECURE_STORE" },
  IOS: { platform: "IOS", mediaCapturePermission: "NSMicrophoneUsageDescription", mediaPlaybackFallback: "LOW_BITRATE", notificationPermission: "UNUserNotificationCenter", shareTarget: "SYSTEM_SHEET", paymentHost: "NATIVE_HOST", storageBackend: "KEYCHAIN" },
  HARMONYOS: { platform: "HARMONYOS", mediaCapturePermission: "ohos.permission.MICROPHONE", mediaPlaybackFallback: "TEXT", notificationPermission: "ohos.permission.NOTIFICATION_CONTROLLER", shareTarget: "HOST_BRIDGE", paymentHost: "NATIVE_HOST", storageBackend: "HARMONY_STORE" },
  MINI_PROGRAM: { platform: "MINI_PROGRAM", mediaCapturePermission: "scope.record", mediaPlaybackFallback: "TEXT", notificationPermission: "subscribeMessage", shareTarget: "HOST_BRIDGE", paymentHost: "MINI_PROGRAM_HOST", storageBackend: "MINI_PROGRAM_STORAGE" },
};

export function createAndroidCapabilityAdapters(options: Omit<CapabilityAdapterOptions, "context"> & { context?: Omit<CapabilityRuntimeContext, "platform"> }): PlatformCapabilityAdapters {
  return createCapabilityAdapters({ ...options, context: { ...options.context, platform: "ANDROID" } as CapabilityRuntimeContext });
}

export function createIosCapabilityAdapters(options: Omit<CapabilityAdapterOptions, "context"> & { context?: Omit<CapabilityRuntimeContext, "platform"> }): PlatformCapabilityAdapters {
  return createCapabilityAdapters({ ...options, context: { ...options.context, platform: "IOS" } as CapabilityRuntimeContext });
}

export function createHarmonyCapabilityAdapters(options: Omit<CapabilityAdapterOptions, "context"> & { context?: Omit<CapabilityRuntimeContext, "platform"> }): PlatformCapabilityAdapters {
  return createCapabilityAdapters({ ...options, context: { ...options.context, platform: "HARMONYOS" } as CapabilityRuntimeContext });
}

/** Upper-case alias keeps the public name aligned with the platform id. */
export const createHarmonyOSCapabilityAdapters = createHarmonyCapabilityAdapters;

export function createMiniProgramCapabilityAdapters(options: Omit<CapabilityAdapterOptions, "context"> & { context?: Omit<CapabilityRuntimeContext, "platform"> }): PlatformCapabilityAdapters {
  return createCapabilityAdapters({ ...options, context: { ...options.context, platform: "MINI_PROGRAM" } as CapabilityRuntimeContext });
}

export function createPlatformCapabilityRegistry(context: CapabilityRuntimeContext, options: Omit<CapabilityAdapterOptions, "context"> & { synthetic?: boolean } = {}): CapabilityRegistry {
  const adapterOptions = { ...options, context } as CapabilityAdapterOptions & { synthetic?: boolean };
  const adapters = createCapabilityAdapters(adapterOptions);
  return createCapabilityRegistry(context, adapters);
}

export const createPlatformCapabilityAdapters = createCapabilityAdapters;
