import {
  capabilityAvailable,
  capabilityFailure,
  capabilityFallback,
  type CapabilityById,
  type CapabilityDescriptor,
  type CapabilityId,
  type CapabilityResult,
  type CapabilityRuntimeContext,
  type CapabilityState,
  type CapabilityStatus,
  type MediaCaptureCapability,
  type MediaPlaybackCapability,
  type NotificationCapability,
  type PaymentCapability,
  type PlatformCapabilityAdapters,
  type PlatformId,
  type SharingCapability,
  type StorageCapability,
} from "./contracts";

export interface CapabilityAdapterOptions {
  context: CapabilityRuntimeContext;
  /** Explicit test/dev simulation. Never inferred from NODE_ENV. */
  synthetic?: boolean;
  lowBandwidth?: boolean;
  deniedCapabilities?: readonly CapabilityId[];
  fallbackCapabilities?: readonly CapabilityId[];
}

const PERMISSIONS: Record<CapabilityId, readonly string[]> = {
  MEDIA_CAPTURE: ["camera", "microphone", "photos"],
  MEDIA_PLAYBACK: ["audio-session"],
  NOTIFICATIONS: ["notifications"],
  SHARING: ["system-share"],
  PAYMENTS: ["host-payment"],
  STORAGE: ["secure-storage"],
};

export function createUnavailableCapabilityAdapters(platform: PlatformId, reason = "平台能力适配器尚未配置"): PlatformCapabilityAdapters {
  const descriptor = (id: CapabilityId): CapabilityDescriptor => ({
    id,
    platform,
    adapterVersion: "unavailable.v1",
    state: "UNAVAILABLE",
    synthetic: false,
    permissions: PERMISSIONS[id],
  });
  const unavailable = <T>(id: CapabilityId): Promise<CapabilityResult<T>> => Promise.resolve(capabilityFailure("UNAVAILABLE", "ADAPTER_NOT_CONFIGURED", `${reason}：${id}`, false, "请使用文字记录或稍后重试。"));
  const status = (id: CapabilityId): Promise<CapabilityResult<CapabilityStatus>> => Promise.resolve(capabilityFailure("UNAVAILABLE", "CAPABILITY_UNAVAILABLE", `${reason}：${id}`, false, "请稍后重试。"));
  const base = (id: CapabilityId) => ({ descriptor: descriptor(id), status: () => status(id) });

  const mediaCapture: MediaCaptureCapability = {
    ...base("MEDIA_CAPTURE"),
    requestPermission: (kind, consentRef) => unavailable("MEDIA_CAPTURE"),
    capture: (request) => unavailable("MEDIA_CAPTURE"),
  };
  const mediaPlayback: MediaPlaybackCapability = {
    ...base("MEDIA_PLAYBACK"),
    play: (source) => unavailable("MEDIA_PLAYBACK"),
    pause: (mediaRef) => unavailable("MEDIA_PLAYBACK"),
    stop: (mediaRef) => unavailable("MEDIA_PLAYBACK"),
  };
  const notifications: NotificationCapability = {
    ...base("NOTIFICATIONS"),
    requestPermission: () => unavailable("NOTIFICATIONS"),
    schedule: (request) => unavailable("NOTIFICATIONS"),
    cancel: (notificationRef) => unavailable("NOTIFICATIONS"),
  };
  const sharing: SharingCapability = { ...base("SHARING"), share: (request) => unavailable("SHARING") };
  const payments: PaymentCapability = {
    ...base("PAYMENTS"),
    prepare: (request) => unavailable("PAYMENTS"),
    confirm: (request) => unavailable("PAYMENTS"),
  };
  const storage: StorageCapability = {
    ...base("STORAGE"),
    get: (key) => unavailable("STORAGE"),
    set: (key, value) => unavailable("STORAGE"),
    remove: (key) => unavailable("STORAGE"),
  };
  return { mediaCapture, mediaPlayback, notifications, sharing, payments, storage };
}

export function createSyntheticCapabilityAdapters(options: CapabilityAdapterOptions): PlatformCapabilityAdapters {
  const { context } = options;
  const denied = new Set(options.deniedCapabilities ?? []);
  const fallback = new Set(options.fallbackCapabilities ?? []);
  const lowBandwidth = options.lowBandwidth === true;

  const descriptor = (id: CapabilityId): CapabilityDescriptor => ({
    id,
    platform: context.platform,
    adapterVersion: "synthetic.v1",
    state: stateFor(id),
    synthetic: true,
    permissions: PERMISSIONS[id],
  });

  function stateFor(id: CapabilityId): CapabilityState {
    if (denied.has(id)) return "PERMISSION_DENIED";
    if (id === "MEDIA_PLAYBACK" && lowBandwidth) return "LOW_BANDWIDTH";
    if (fallback.has(id)) return "FALLBACK";
    return "AVAILABLE";
  }

  function statusFor(id: CapabilityId): Promise<CapabilityResult<CapabilityStatus>> {
    const state = stateFor(id);
    if (state === "PERMISSION_DENIED") return Promise.resolve(capabilityFailure("PERMISSION_DENIED", "PERMISSION_DENIED", `${id} 权限未授予`, true, "请在系统设置中允许后重试。"));
    if (state === "LOW_BANDWIDTH") return Promise.resolve(capabilityFailure("LOW_BANDWIDTH", "LOW_BANDWIDTH", "当前网络较慢，媒体播放已暂停", true, "可切换文字或低码率内容。"));
    const value = { state, permission: "GRANTED" as const, lowBandwidth, fallbackSupported: state === "FALLBACK" || lowBandwidth };
    return Promise.resolve(state === "FALLBACK" ? capabilityFallback(value, "将回退到宿主或本地能力。") : { state, value });
  }

  function gate<T>(id: CapabilityId, value: T, fallbackMessage?: string): CapabilityResult<T> {
    const state = stateFor(id);
    if (state === "PERMISSION_DENIED") return capabilityFailure("PERMISSION_DENIED", "PERMISSION_DENIED", `${id} 权限未授予`, true, "请在系统设置中允许后重试。");
    if (state === "LOW_BANDWIDTH") return capabilityFailure("LOW_BANDWIDTH", "LOW_BANDWIDTH", "当前网络较慢，暂不能完成媒体操作", true, "可切换文字或低码率内容。");
    if (state === "FALLBACK") return capabilityFallback(value, fallbackMessage ?? "将回退到宿主或本地能力。");
    return capabilityAvailable(value);
  }

  const mediaIds = new Map<string, "PLAYING" | "PAUSED" | "STOPPED">();
  const mediaCapture: MediaCaptureCapability = {
    descriptor: descriptor("MEDIA_CAPTURE"),
    status: () => statusFor("MEDIA_CAPTURE"),
    requestPermission: async (kind, consentRef) => {
      const result = gate("MEDIA_CAPTURE", { permission: "GRANTED" as const, kind, consentRef });
      return result;
    },
    capture: async (request) => {
      if (!request.consentRef.trim() || !request.contentLocale.trim()) return capabilityFailure("UNAVAILABLE", "INVALID_REQUEST", "媒体采集需要 consentRef 与 contentLocale", false);
      return gate("MEDIA_CAPTURE", {
        mediaRef: `synthetic-media-${request.kind.toLowerCase()}`,
        kind: request.kind,
        contentLocale: request.contentLocale,
        uri: `synthetic://${request.kind.toLowerCase()}`,
        synthetic: true,
        visibility: "FAMILY_PRIVATE" as const,
      }, "可改用文字记录，不上传真实媒体。");
    },
  };
  const mediaPlayback: MediaPlaybackCapability = {
    descriptor: descriptor("MEDIA_PLAYBACK"),
    status: () => statusFor("MEDIA_PLAYBACK"),
    play: async (source) => {
      mediaIds.set(source.mediaRef, "PLAYING");
      return gate("MEDIA_PLAYBACK", { mediaRef: source.mediaRef, state: "PLAYING" as const, synthetic: true }, "可改用文字或低码率内容。");
    },
    pause: async (mediaRef) => {
      mediaIds.set(mediaRef, "PAUSED");
      return gate("MEDIA_PLAYBACK", { mediaRef, state: "PAUSED" as const, synthetic: true }, "播放已回退为本地控制。");
    },
    stop: async (mediaRef) => {
      mediaIds.set(mediaRef, "STOPPED");
      return gate("MEDIA_PLAYBACK", { mediaRef, state: "STOPPED" as const, synthetic: true }, "播放已回退为本地控制。");
    },
  };

  const notificationsStore = new Map<string, string>();
  const notifications: NotificationCapability = {
    descriptor: descriptor("NOTIFICATIONS"),
    status: () => statusFor("NOTIFICATIONS"),
    requestPermission: async () => gate("NOTIFICATIONS", { permission: "GRANTED" as const }),
    schedule: async (request) => {
      notificationsStore.set(request.notificationRef, request.body);
      return gate("NOTIFICATIONS", { notificationRef: request.notificationRef, scheduled: true, externalEffect: false, synthetic: true }, "已保存在本机演示队列，不发送真实通知。");
    },
    cancel: async (notificationRef) => {
      const cancelled = notificationsStore.delete(notificationRef);
      return gate("NOTIFICATIONS", { notificationRef, cancelled });
    },
  };

  const sharing: SharingCapability = {
    descriptor: descriptor("SHARING"),
    status: () => statusFor("SHARING"),
    share: async (request) => gate("SHARING", { shareRef: request.shareRef, shared: false, externalEffect: false, synthetic: true }, "请由家庭确认后使用宿主分享；演示环境不外发内容。"),
  };

  const payments: PaymentCapability = {
    descriptor: descriptor("PAYMENTS"),
    status: () => statusFor("PAYMENTS"),
    prepare: async (request) => {
      if (!request.productRef.trim() || !request.currency.trim() || request.amountMinor < 0 || !request.consentRef.trim() || !request.idempotencyKey.trim()) return capabilityFailure("UNAVAILABLE", "INVALID_REQUEST", "支付意向需要完整的产品、金额、授权与幂等信息", false);
      return gate("PAYMENTS", { intentRef: request.intentRef, status: "PREPARED" as const, externalEffect: false, synthetic: true }, "只保存支付草案，不发起真实扣款。");
    },
    confirm: async (request) => {
      const receipt = { intentRef: request.intentRef, status: "UNAVAILABLE" as const, externalEffect: false, synthetic: true };
      const gated = gate("PAYMENTS", receipt, "需要宿主明确确认；演示环境不会扣款。");
      return gated.state === "AVAILABLE" ? capabilityFallback(receipt, "需要宿主明确确认；演示环境不会扣款。") : gated;
    },
  };

  const storageStore = new Map<string, string>();
  const storage: StorageCapability = {
    descriptor: descriptor("STORAGE"),
    status: () => statusFor("STORAGE"),
    get: async (key) => {
      if (!key.trim()) return capabilityFailure("UNAVAILABLE", "INVALID_REQUEST", "storage key 不能为空", false);
      return gate("STORAGE", { key, value: storageStore.get(key) ?? null });
    },
    set: async (key, value) => {
      if (!key.trim()) return capabilityFailure("UNAVAILABLE", "INVALID_REQUEST", "storage key 不能为空", false);
      storageStore.set(key, value);
      return gate("STORAGE", { key, persisted: true });
    },
    remove: async (key) => {
      const removed = storageStore.delete(key);
      return gate("STORAGE", { key, removed });
    },
  };

  return { mediaCapture, mediaPlayback, notifications, sharing, payments, storage };
}

export type SyntheticCapabilityOverrides = Partial<{ [K in CapabilityId]: CapabilityState }>;

/** Convenience factory used by tests and local demos; production must inject a real adapter. */
export function createCapabilityAdapters(options: CapabilityAdapterOptions & { synthetic?: boolean }): PlatformCapabilityAdapters {
  if (options.synthetic) return createSyntheticCapabilityAdapters(options);
  return createUnavailableCapabilityAdapters(options.context.platform);
}

export function capabilityMap(adapters: PlatformCapabilityAdapters): CapabilityById {
  return {
    MEDIA_CAPTURE: adapters.mediaCapture,
    MEDIA_PLAYBACK: adapters.mediaPlayback,
    NOTIFICATIONS: adapters.notifications,
    SHARING: adapters.sharing,
    PAYMENTS: adapters.payments,
    STORAGE: adapters.storage,
  };
}
