import { ProductStudioApiError, type ProductStudioFetch } from "./api";

export type CommerceOrderIntent = { order_intent_id: string; status: string; product_ref: string; product_version: number; created_at: string };
export type CommerceEntitlement = { entitlement_id: string; status: string; source_order_intent_id: string; available_at: string | null; expires_at: string | null };
export type CommerceProjection = { family_id: string; projection_version: number; visibility: "FAMILY_PRIVATE"; order_intents: CommerceOrderIntent[]; entitlements: CommerceEntitlement[]; evidence_receipt_refs: string[]; text_equivalent: string; read_only: true };

export interface CommerceProjectionApiClient { get(familyId: string): Promise<CommerceProjection>; }
type Options = { baseUrl?: string; fetchImpl?: ProductStudioFetch; authorization?: string; tenantScope?: string };

function validate(value: unknown): CommerceProjection {
  if (!value || typeof value !== "object") throw new ProductStudioApiError("INVALID_RESPONSE", "商业交付投影无效。");
  const row = value as Record<string, unknown>;
  if (typeof row.family_id !== "string" || row.visibility !== "FAMILY_PRIVATE" || row.read_only !== true
    || !Number.isInteger(row.projection_version) || !Array.isArray(row.order_intents) || !Array.isArray(row.entitlements)
    || !Array.isArray(row.evidence_receipt_refs) || row.evidence_receipt_refs.some((ref) => typeof ref !== "string")
    || typeof row.text_equivalent !== "string") throw new ProductStudioApiError("INVALID_RESPONSE", "商业交付投影字段无效。");
  return { family_id: row.family_id, projection_version: row.projection_version as number, visibility: "FAMILY_PRIVATE", read_only: true,
    text_equivalent: row.text_equivalent, evidence_receipt_refs: row.evidence_receipt_refs as string[], order_intents: row.order_intents as CommerceOrderIntent[], entitlements: row.entitlements as CommerceEntitlement[] };
}

export class HttpCommerceProjectionApiClient implements CommerceProjectionApiClient {
  private readonly baseUrl: string; private readonly fetchImpl: ProductStudioFetch; private readonly headers: HeadersInit;
  constructor(options: Options = {}) { this.baseUrl = options.baseUrl ?? ""; this.fetchImpl = options.fetchImpl ?? fetch; this.headers = { ...(options.authorization ? { authorization: options.authorization } : {}), ...(options.tenantScope ? { "x-tenant-scope": options.tenantScope } : {}) }; }
  async get(familyId: string): Promise<CommerceProjection> {
    const response = await this.fetchImpl(`${this.baseUrl}/families/${encodeURIComponent(familyId)}/commerce/projection`, { headers: this.headers });
    if (!response.ok) throw new ProductStudioApiError(response.status === 403 ? "FORBIDDEN" : response.status === 404 ? "NOT_FOUND" : "UNAVAILABLE", "家庭商业交付投影暂不可读取。", response.status);
    return validate(await response.json());
  }
}
