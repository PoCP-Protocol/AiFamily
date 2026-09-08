export type CommercialReadinessInput = {
  lesson_count: number;
  courseware_approved: boolean;
  product_package_released: boolean;
  evidence_verified: boolean;
  payment_sandbox_verified: boolean;
  entitlement_grant_verified: boolean;
  delivery_readback_verified: boolean;
  refund_recovery_verified: boolean;
  human_gate_accepted: boolean;
};

export type CommercialReadiness = {
  ready: boolean;
  checks: Record<string, boolean>;
  blockers: string[];
};

export async function fetchCommercialReadiness(
  input: CommercialReadinessInput,
  fetchImpl: typeof fetch = fetch,
): Promise<CommercialReadiness> {
  const response = await fetchImpl("/product-intelligence/courses/commercial-readiness", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error(`commercial_readiness_http_${response.status}`);
  const result = await response.json() as CommercialReadiness;
  if (typeof result.ready !== "boolean" || !result.checks || !Array.isArray(result.blockers)) {
    throw new Error("commercial_readiness_invalid_response");
  }
  return result;
}
