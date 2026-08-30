import type {
  CapabilityId,
  CapabilityResult,
  CapabilityRuntimeContext,
  CapabilityState,
  CapabilityStatus,
} from "./contracts";
import type { CapabilityRegistry } from "./registry";

/** Stable status vocabulary consumed by a shell/status card. */
export type CapabilityHealthStatus = "AVAILABLE" | "PERMISSION_DENIED" | "LOW_BANDWIDTH" | "FALLBACK" | "NOT_CONFIGURED";

export interface CapabilityHealthCard {
  id: CapabilityId;
  platform: CapabilityRuntimeContext["platform"];
  locale: string;
  status: CapabilityHealthStatus;
  /** Stable i18n keys; clients resolve these using their locale catalogs. */
  titleKey: `platform_capability.${CapabilityId}.title`;
  messageKey: `platform_capability.${CapabilityId}.${CapabilityHealthStatus}.message`;
  retryable: boolean;
  externalEffect: boolean;
  synthetic: boolean;
  fallback?: string;
  errorCode?: string;
}

const EXTERNAL_EFFECT_CAPABILITIES: ReadonlySet<CapabilityId> = new Set(["NOTIFICATIONS", "SHARING", "PAYMENTS"]);

export function healthStatusFromResult(result: CapabilityResult<CapabilityStatus>): CapabilityHealthStatus {
  if (result.state === "AVAILABLE") return "AVAILABLE";
  if (result.state === "PERMISSION_DENIED") return "PERMISSION_DENIED";
  if (result.state === "LOW_BANDWIDTH") return "LOW_BANDWIDTH";
  if (result.state === "FALLBACK") return "FALLBACK";
  return "NOT_CONFIGURED";
}

export function mapCapabilityHealthCard(
  id: CapabilityId,
  context: CapabilityRuntimeContext,
  descriptor: { synthetic: boolean },
  result: CapabilityResult<CapabilityStatus>,
): CapabilityHealthCard {
  const status = healthStatusFromResult(result);
  const error = result.error;
  return {
    id,
    platform: context.platform,
    locale: normalizeLocale(context.locale),
    status,
    titleKey: `platform_capability.${id}.title`,
    messageKey: `platform_capability.${id}.${status}.message`,
    retryable: error?.retryable ?? (status === "LOW_BANDWIDTH" || status === "PERMISSION_DENIED"),
    // Synthetic adapters never cause an external side effect. Real adapter
    // risk is declared by capability type, not by a family/business rule.
    externalEffect: !descriptor.synthetic && EXTERNAL_EFFECT_CAPABILITIES.has(id),
    synthetic: descriptor.synthetic,
    fallback: result.fallback,
    errorCode: error?.code,
  };
}

export async function buildCapabilityHealthCards(registry: CapabilityRegistry): Promise<CapabilityHealthCard[]> {
  const descriptors = new Map(registry.descriptors().map((descriptor) => [descriptor.id, descriptor]));
  let snapshot: Awaited<ReturnType<CapabilityRegistry["statusSnapshot"]>>;
  try {
    snapshot = await registry.statusSnapshot();
  } catch {
    // A shell still receives a safe, retryable card if the health probe itself
    // fails. This is an adapter/transport failure, not a business decision.
    return (Object.keys(Object.fromEntries(descriptors)) as CapabilityId[]).map((id) => mapCapabilityHealthCard(id, registry.context, descriptors.get(id) ?? { synthetic: false }, {
      state: "UNAVAILABLE",
      error: { code: "CAPABILITY_UNAVAILABLE", message: "health probe failed", retryable: true },
      fallback: "稍后重试能力探测。",
    }));
  }
  return (Object.keys(snapshot) as CapabilityId[]).map((id) => mapCapabilityHealthCard(id, registry.context, descriptors.get(id) ?? { synthetic: false }, snapshot[id]));
}

export function normalizeLocale(locale: string) {
  const value = locale.trim();
  if (!value) return "en-US";
  // Keep this deliberately small and BCP-47-shaped; Intl accepts arbitrary
  // three-part private tags that are not useful as UI catalog keys.
  if (!/^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/.test(value)) return "en-US";
  try {
    return Intl.getCanonicalLocales(value)[0] ?? "en-US";
  } catch {
    return "en-US";
  }
}

export function isRetryableHealthStatus(status: CapabilityHealthStatus) {
  return status === "PERMISSION_DENIED" || status === "LOW_BANDWIDTH";
}

export function isCapabilityState(value: string): value is CapabilityState {
  return value === "AVAILABLE" || value === "UNAVAILABLE" || value === "PERMISSION_DENIED" || value === "LOW_BANDWIDTH" || value === "FALLBACK";
}
