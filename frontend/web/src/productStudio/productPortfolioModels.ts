import { ProductStudioApiError } from "./api";

export type CatalogItemKind = "COMPONENT" | "SKILL";
export type CatalogSelectionState = "REUSABLE" | "REVIEW_REQUIRED" | "NOT_APPLICABLE";

export type CatalogAdmissionReceipt = {
  receipt_id: string;
  content_hash: string;
  outcome: "ADMITTED" | "REVIEW_REQUIRED" | "BLOCKED";
  policy_version: string;
  valid_until: string;
};

export type VersionedCatalogItem = {
  item_kind: CatalogItemKind;
  item_ref: string;
  logical_id: string;
  version: string;
  content_hash: string;
  title: string;
  source_lifecycle_state: string;
  server_selection_state: CatalogSelectionState;
  reason_codes: string[];
  owner_ref: string;
  purpose: string;
  zone: "HOMOGENEOUS" | "ADVANTAGE" | "UNIQUE_CANDIDATE";
  target_roles: string[];
  executor_roles: string[];
  age_bands: string[];
  scenarios: string[];
  regions: string[];
  locales: string[];
  preconditions: string[];
  contraindications: string[];
  admission_receipts: CatalogAdmissionReceipt[];
  required_skill_refs: string[];
  allowed_tools: string[];
  forbidden_tools: string[];
  human_handoff_policy: string;
  updated_at: string;
};

export type VersionedCatalogSnapshot = {
  schema_version: "1.0";
  snapshot_id: string;
  content_hash: string;
  tenant_scope: string;
  purpose: "PRODUCT_PACKAGE_COMPOSITION";
  policy_version: string;
  target_context_hash: string;
  evaluated_for: { draft_id: string; version: string; content_hash: string };
  generated_at: string;
  expires_at: string;
  items: VersionedCatalogItem[];
};

export type CatalogSelectionDraft = {
  catalog_snapshot_id: string;
  catalog_content_hash: string;
  target_context_hash: string;
  component_refs: string[];
  skill_refs: string[];
};

const SHA256 = /^[0-9a-f]{64}$/;
const ITEM_KINDS = new Set(["COMPONENT", "SKILL"]);
const SELECTION_STATES = new Set(["REUSABLE", "REVIEW_REQUIRED", "NOT_APPLICABLE"]);
const RECEIPT_OUTCOMES = new Set(["ADMITTED", "REVIEW_REQUIRED", "BLOCKED"]);
const ZONES = new Set(["HOMOGENEOUS", "ADVANTAGE", "UNIQUE_CANDIDATE"]);

function invalid(message: string): never {
  throw new ProductStudioApiError("INVALID_RESPONSE", message);
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return invalid(`${label} 不是对象。`);
  return value as Record<string, unknown>;
}

function stringValue(value: unknown, label: string): string {
  if (typeof value !== "string" || !value.trim()) return invalid(`${label} 缺失。`);
  return value.trim();
}

function enumValue<T extends string>(value: unknown, allowed: Set<string>, label: string): T {
  const normalized = stringValue(value, label);
  if (!allowed.has(normalized)) return invalid(`${label} 包含未知状态。`);
  return normalized as T;
}

function awareTimestamp(value: unknown, label: string): string {
  const normalized = stringValue(value, label);
  if (!/(?:Z|[+-]\d{2}:\d{2})$/.test(normalized) || Number.isNaN(Date.parse(normalized))) {
    return invalid(`${label} 不是带时区时间。`);
  }
  return normalized;
}

function hash(value: unknown, label: string): string {
  const normalized = stringValue(value, label);
  if (!SHA256.test(normalized)) return invalid(`${label} 不是 SHA-256。`);
  return normalized;
}

function strings(value: unknown, label: string, allowEmpty = true): string[] {
  if (!Array.isArray(value) || (!allowEmpty && value.length === 0)) return invalid(`${label} 缺失。`);
  const normalized = value.map((item) => stringValue(item, label));
  if (new Set(normalized).size !== normalized.length) return invalid(`${label} 包含重复引用。`);
  return normalized;
}

function parseReceipt(value: unknown): CatalogAdmissionReceipt {
  const source = record(value, "admission_receipt");
  return {
    receipt_id: stringValue(source.receipt_id, "receipt_id"),
    content_hash: hash(source.content_hash, "receipt content_hash"),
    outcome: enumValue(source.outcome, RECEIPT_OUTCOMES, "receipt outcome"),
    policy_version: stringValue(source.policy_version, "receipt policy_version"),
    valid_until: awareTimestamp(source.valid_until, "receipt valid_until"),
  };
}

function parseItem(value: unknown): VersionedCatalogItem {
  const source = record(value, "catalog item");
  const allowedTools = strings(source.allowed_tools, "allowed_tools");
  const forbiddenTools = strings(source.forbidden_tools, "forbidden_tools");
  if (allowedTools.some((tool) => forbiddenTools.includes(tool))) return invalid("目录条目的允许与禁止工具发生冲突。");
  if (!Array.isArray(source.admission_receipts) || source.admission_receipts.length === 0) {
    return invalid("目录条目缺少 receipt-backed admission。");
  }
  const selectionState = enumValue<CatalogSelectionState>(source.server_selection_state, SELECTION_STATES, "server_selection_state");
  const reasonCodes = strings(source.reason_codes, "reason_codes");
  if (selectionState !== "REUSABLE" && reasonCodes.length === 0) return invalid("不可直接复用的条目缺少服务端 reason code。");
  return {
    item_kind: enumValue(source.item_kind, ITEM_KINDS, "item_kind"),
    item_ref: stringValue(source.item_ref, "item_ref"),
    logical_id: stringValue(source.logical_id, "logical_id"),
    version: stringValue(source.version, "version"),
    content_hash: hash(source.content_hash, "item content_hash"),
    title: stringValue(source.title, "title"),
    source_lifecycle_state: stringValue(source.source_lifecycle_state, "source_lifecycle_state"),
    server_selection_state: selectionState,
    reason_codes: reasonCodes,
    owner_ref: stringValue(source.owner_ref, "owner_ref"),
    purpose: stringValue(source.purpose, "purpose"),
    zone: enumValue(source.zone, ZONES, "zone"),
    target_roles: strings(source.target_roles, "target_roles", false),
    executor_roles: strings(source.executor_roles, "executor_roles", false),
    age_bands: strings(source.age_bands, "age_bands", false),
    scenarios: strings(source.scenarios, "scenarios", false),
    regions: strings(source.regions, "regions", false),
    locales: strings(source.locales, "locales", false),
    preconditions: strings(source.preconditions, "preconditions"),
    contraindications: strings(source.contraindications, "contraindications"),
    admission_receipts: source.admission_receipts.map(parseReceipt),
    required_skill_refs: strings(source.required_skill_refs, "required_skill_refs"),
    allowed_tools: allowedTools,
    forbidden_tools: forbiddenTools,
    human_handoff_policy: stringValue(source.human_handoff_policy, "human_handoff_policy"),
    updated_at: awareTimestamp(source.updated_at, "updated_at"),
  };
}

export function validateCatalogSnapshot(value: unknown): VersionedCatalogSnapshot {
  const source = record(value, "catalog snapshot");
  if (source.schema_version !== "1.0" || source.purpose !== "PRODUCT_PACKAGE_COMPOSITION") {
    return invalid("组件与 Skill 目录合同版本或用途无效。");
  }
  const evaluatedFor = record(source.evaluated_for, "evaluated_for");
  const generatedAt = awareTimestamp(source.generated_at, "generated_at");
  const expiresAt = awareTimestamp(source.expires_at, "expires_at");
  if (Date.parse(generatedAt) >= Date.parse(expiresAt)) return invalid("组件与 Skill 目录时间窗口无效。");
  if (!Array.isArray(source.items) || source.items.length === 0) return invalid("目录快照没有版本化条目。");
  const items = source.items.map(parseItem);
  const refs = items.map((item) => item.item_ref);
  if (new Set(refs).size !== refs.length) return invalid("目录快照包含重复版本引用。");
  for (const item of items.filter((candidate) => candidate.server_selection_state === "REUSABLE")) {
    if (item.admission_receipts.some((receipt) => receipt.outcome !== "ADMITTED"
      || Date.parse(receipt.valid_until) < Date.parse(expiresAt))) {
      return invalid("可复用条目的 admission receipt 与目录有效期不一致。");
    }
  }
  for (const component of items.filter((item) => item.item_kind === "COMPONENT")) {
    for (const skillRef of component.required_skill_refs) {
      const skill = items.find((item) => item.item_kind === "SKILL" && item.item_ref === skillRef);
      if (!skill) return invalid("组件依赖的冻结 Skill 引用不在同一目录快照中。");
      if (component.server_selection_state === "REUSABLE" && skill.server_selection_state !== "REUSABLE") {
        return invalid("可复用组件依赖了不可复用的 Skill。");
      }
    }
  }
  return {
    schema_version: "1.0",
    snapshot_id: stringValue(source.snapshot_id, "snapshot_id"),
    content_hash: hash(source.content_hash, "snapshot content_hash"),
    tenant_scope: stringValue(source.tenant_scope, "tenant_scope"),
    purpose: "PRODUCT_PACKAGE_COMPOSITION",
    policy_version: stringValue(source.policy_version, "policy_version"),
    target_context_hash: hash(source.target_context_hash, "target_context_hash"),
    evaluated_for: {
      draft_id: stringValue(evaluatedFor.draft_id, "evaluated_for.draft_id"),
      version: stringValue(evaluatedFor.version, "evaluated_for.version"),
      content_hash: hash(evaluatedFor.content_hash, "evaluated_for.content_hash"),
    },
    generated_at: generatedAt,
    expires_at: expiresAt,
    items,
  };
}
