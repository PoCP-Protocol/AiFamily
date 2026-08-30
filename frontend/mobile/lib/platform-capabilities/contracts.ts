/**
 * Cross-platform capability contracts.
 *
 * These interfaces deliberately contain no business rules. A family journey
 * can depend on a capability interface and render the returned state without
 * knowing whether the adapter is Android, iOS, HarmonyOS, or mini-program.
 */

export const PLATFORM_IDS = ["ANDROID", "IOS", "HARMONYOS", "MINI_PROGRAM"] as const;
export type PlatformId = (typeof PLATFORM_IDS)[number];

export const CAPABILITY_IDS = ["MEDIA_CAPTURE", "MEDIA_PLAYBACK", "NOTIFICATIONS", "SHARING", "PAYMENTS", "STORAGE"] as const;
export type CapabilityId = (typeof CAPABILITY_IDS)[number];

export type CapabilityEnvironment = "DEV" | "TEST" | "PROD";
export type CapabilityState = "AVAILABLE" | "UNAVAILABLE" | "PERMISSION_DENIED" | "LOW_BANDWIDTH" | "FALLBACK";
export type PermissionState = "GRANTED" | "DENIED" | "UNKNOWN";

export type CapabilityErrorCode =
  | "CAPABILITY_UNAVAILABLE"
  | "PERMISSION_DENIED"
  | "LOW_BANDWIDTH"
  | "ADAPTER_NOT_CONFIGURED"
  | "USER_CANCELLED"
  | "INVALID_REQUEST"
  | "HOST_CONFIRMATION_REQUIRED"
  | "STORAGE_READ_FAILED"
  | "STORAGE_WRITE_FAILED";

export interface CapabilityError {
  code: CapabilityErrorCode;
  message: string;
  retryable: boolean;
}

export interface CapabilityResult<T> {
  state: CapabilityState;
  value?: T;
  error?: CapabilityError;
  /** A human-readable next step, not an instruction to call a provider. */
  fallback?: string;
}

export interface CapabilityRuntimeContext {
  platform: PlatformId;
  environment: CapabilityEnvironment;
  locale: string;
  /** Optional opaque tenant scope; adapters must not infer or mutate it. */
  tenantScope?: string;
}

export interface CapabilityDescriptor {
  id: CapabilityId;
  platform: PlatformId;
  adapterVersion: string;
  state: CapabilityState;
  synthetic: boolean;
  permissions: readonly string[];
}

export interface CapabilityStatus {
  state: CapabilityState;
  permission: PermissionState;
  lowBandwidth: boolean;
  fallbackSupported: boolean;
}

export interface CapabilityBase {
  readonly descriptor: CapabilityDescriptor;
  status(): Promise<CapabilityResult<CapabilityStatus>>;
}

export type MediaKind = "VOICE" | "IMAGE" | "AUDIO" | "VIDEO" | "TEXT" | "INTERACTIVE_CARD";

export interface MediaPermissionReceipt {
  permission: PermissionState;
  kind: MediaKind;
  consentRef: string | null;
}

export interface MediaCaptureRequest {
  kind: Exclude<MediaKind, "TEXT" | "INTERACTIVE_CARD">;
  consentRef: string;
  contentLocale: string;
  maxDurationMs?: number;
}

export interface MediaAsset {
  mediaRef: string;
  kind: MediaCaptureRequest["kind"];
  contentLocale: string;
  uri: string;
  synthetic: boolean;
  visibility: "FAMILY_PRIVATE";
}

export interface MediaCaptureCapability extends CapabilityBase {
  requestPermission(kind: MediaCaptureRequest["kind"], consentRef: string | null): Promise<CapabilityResult<MediaPermissionReceipt>>;
  capture(request: MediaCaptureRequest): Promise<CapabilityResult<MediaAsset>>;
}

export interface MediaPlaybackSource {
  mediaRef: string;
  kind: MediaKind;
  uri?: string;
  contentLocale?: string;
}

export interface MediaPlaybackReceipt {
  mediaRef: string;
  state: "PLAYING" | "PAUSED" | "STOPPED";
  synthetic: boolean;
}

export interface MediaPlaybackCapability extends CapabilityBase {
  play(source: MediaPlaybackSource): Promise<CapabilityResult<MediaPlaybackReceipt>>;
  pause(mediaRef: string): Promise<CapabilityResult<MediaPlaybackReceipt>>;
  stop(mediaRef: string): Promise<CapabilityResult<MediaPlaybackReceipt>>;
}

export interface NotificationRequest {
  notificationRef: string;
  title: string;
  body: string;
  scheduledAt?: string;
  locale: string;
}

export interface NotificationReceipt {
  notificationRef: string;
  scheduled: boolean;
  externalEffect: boolean;
  synthetic: boolean;
}

export interface NotificationCapability extends CapabilityBase {
  requestPermission(): Promise<CapabilityResult<{ permission: PermissionState }>>;
  schedule(request: NotificationRequest): Promise<CapabilityResult<NotificationReceipt>>;
  cancel(notificationRef: string): Promise<CapabilityResult<{ notificationRef: string; cancelled: boolean }>>;
}

export interface ShareRequest {
  shareRef: string;
  title?: string;
  text?: string;
  url?: string;
  contentLocale: string;
}

export interface ShareReceipt {
  shareRef: string;
  shared: boolean;
  externalEffect: boolean;
  synthetic: boolean;
}

export interface SharingCapability extends CapabilityBase {
  share(request: ShareRequest): Promise<CapabilityResult<ShareReceipt>>;
}

export interface PaymentIntentRequest {
  intentRef: string;
  productRef: string;
  currency: string;
  amountMinor: number;
  consentRef: string;
  idempotencyKey: string;
}

export interface PaymentIntentReceipt {
  intentRef: string;
  status: "PREPARED" | "REQUIRES_HOST_CONFIRMATION" | "UNAVAILABLE";
  externalEffect: boolean;
  synthetic: boolean;
}

export interface PaymentConfirmationRequest {
  intentRef: string;
  hostConfirmationToken: string;
}

export interface PaymentConfirmationReceipt {
  intentRef: string;
  status: "CONFIRMED" | "CANCELLED" | "UNAVAILABLE";
  externalEffect: boolean;
  synthetic: boolean;
}

export interface PaymentCapability extends CapabilityBase {
  prepare(request: PaymentIntentRequest): Promise<CapabilityResult<PaymentIntentReceipt>>;
  confirm(request: PaymentConfirmationRequest): Promise<CapabilityResult<PaymentConfirmationReceipt>>;
}

export interface StorageCapability extends CapabilityBase {
  get(key: string): Promise<CapabilityResult<{ key: string; value: string | null }>>;
  set(key: string, value: string): Promise<CapabilityResult<{ key: string; persisted: boolean }>>;
  remove(key: string): Promise<CapabilityResult<{ key: string; removed: boolean }>>;
}

export interface PlatformCapabilityAdapters {
  mediaCapture: MediaCaptureCapability;
  mediaPlayback: MediaPlaybackCapability;
  notifications: NotificationCapability;
  sharing: SharingCapability;
  payments: PaymentCapability;
  storage: StorageCapability;
}

export type CapabilityById = {
  MEDIA_CAPTURE: MediaCaptureCapability;
  MEDIA_PLAYBACK: MediaPlaybackCapability;
  NOTIFICATIONS: NotificationCapability;
  SHARING: SharingCapability;
  PAYMENTS: PaymentCapability;
  STORAGE: StorageCapability;
};

export function capabilityAvailable<T>(value: T): CapabilityResult<T> {
  return { state: "AVAILABLE", value };
}

export function capabilityFallback<T>(value: T | undefined, fallback: string): CapabilityResult<T> {
  return { state: "FALLBACK", value, fallback };
}

export function capabilityFailure<T>(state: Exclude<CapabilityState, "AVAILABLE" | "FALLBACK">, code: CapabilityErrorCode, message: string, retryable = false, fallback?: string): CapabilityResult<T> {
  return { state, error: { code, message, retryable }, fallback };
}

