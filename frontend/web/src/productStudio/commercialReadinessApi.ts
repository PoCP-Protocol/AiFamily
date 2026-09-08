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
  evidence_refs?: string[];
};

export type CommercialReadiness = {
  execution_mode: "EVALUATION_ONLY";
  scope: "PILOT_21D" | "FULL_24";
  ready: boolean;
  checks: Record<string, boolean>;
  blockers: string[];
  evidence_refs: string[];
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
  if (!response.ok) {
    if (response.status === 422) throw new Error("证据引用必须使用带版本的格式，例如 evidence:payment@v1");
    throw new Error(`commercial_readiness_http_${response.status}`);
  }
  const result = await response.json() as CommercialReadiness;
  const checksAreValid = result.checks && typeof result.checks === "object"
    && Object.values(result.checks).every((value) => typeof value === "boolean");
  if (result.execution_mode !== "EVALUATION_ONLY"
    || !(result.scope === "PILOT_21D" || result.scope === "FULL_24")
    || typeof result.ready !== "boolean" || !checksAreValid || !Array.isArray(result.blockers)
    || !result.blockers.every((value) => typeof value === "string")
    || !Array.isArray(result.evidence_refs)
    || !result.evidence_refs.every((value) => typeof value === "string")) {
    throw new Error("commercial_readiness_invalid_response");
  }
  return result;
}
