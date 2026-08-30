import type { ProductStudioState } from "./types";

/**
 * Explicitly synthetic fixture for route/component tests. It is not a product
 * record and must never be sent to a backend or presented as market truth.
 */
export const sandboxProductStudioState: ProductStudioState = {
  currentStage: "DEMAND",
  demand: {
    id: "sandbox-demand",
    title: "家庭节奏需求（Sandbox）",
    summary: "合成需求草案：用于演示需求到产品包的审查路径。",
    evidenceRefs: [{ ref: "fixture:demand:001", label: "合成需求样例", kind: "demand", status: "UNKNOWN" }],
    status: "DRAFT",
    provenanceRef: "fixture:product-studio:sandbox",
  },
  market: {
    id: "sandbox-market",
    title: "市场与竞品证据（Sandbox）",
    summary: "合成市场洞察草案；不代表已验证的市场事实。",
    evidenceRefs: [{ ref: "fixture:market:001", label: "合成市场样例", kind: "market", status: "UNKNOWN" }],
    competitorEvidence: [{ ref: "fixture:competitor:001", label: "合成竞品样例", kind: "competitor", status: "UNKNOWN" }],
    status: "DRAFT",
    provenanceRef: "fixture:product-studio:sandbox",
  },
  productPackage: {
    id: "sandbox-package",
    title: "21 天成长营（Sandbox）",
    summary: "合成 ProductPackage 草案，等待 IPD Gate。",
    evidenceRefs: [{ ref: "fixture:package:001", label: "合成试点样例", kind: "experiment", status: "UNKNOWN" }],
    status: "DRAFT",
    zone: "ADVANTAGE",
    durationDays: 21,
    provenanceRef: "fixture:product-studio:sandbox",
  },
  gate: {
    decision: null,
    evidenceRefs: [{ ref: "fixture:gate:001", label: "合成 Gate 样例", kind: "experiment", status: "UNKNOWN" }],
  },
  plm: {
    recommendation: null,
    evidenceRefs: [{ ref: "fixture:pilot:001", label: "合成试点样例", kind: "pilot", status: "UNKNOWN" }],
  },
};

