/**
 * UI-13..UI-18 projection of docs/03_product/FUNCTIONAL_DECOMPOSITION.md.
 *
 * This is intentionally a small, executable view of the canonical document,
 * not a replacement for it. It constrains layout and action semantics for the
 * commerce batch while the corresponding capabilities are frozen or draft-only.
 */
export type UiLayoutMode = "CATALOG" | "DETAIL" | "PRIVATE_DRAFT" | "BOUNDARY" | "READ_ONLY";
export type UiActionPolicy = "NAVIGATE_ONLY" | "SAVE_PRIVATE_DRAFT" | "CONTROLLED_INTENT" | "NO_VALUE_MUTATION" | "READ_ONLY";

export interface UiFunctionalHierarchy {
  uiId: `UI-${string}`;
  l1: string;
  l2: readonly string[];
  l3: readonly string[];
  l4: readonly string[];
  capabilityState: "FROZEN" | "SYNTHETIC_ONLY" | "GATE_BOUNDARY" | "READ_ONLY";
  layoutMode: UiLayoutMode;
  actionPolicy: UiActionPolicy;
}

export const COMMERCE_UI_FUNCTIONAL_HIERARCHY = {
  "UI-13": {
    uiId: "UI-13",
    l1: "5 COMMERCE 商业化",
    l2: ["5.1 商品目录"],
    l3: ["5.1.1 商品列表"],
    l4: ["GET /families/{id}/commerce/products"],
    capabilityState: "FROZEN",
    layoutMode: "CATALOG",
    actionPolicy: "NAVIGATE_ONLY",
  },
  "UI-14": {
    uiId: "UI-14",
    l1: "5 COMMERCE 商业化",
    l2: ["5.1 商品目录", "5.2 下单意图"],
    l3: ["5.1.2 商品投影", "5.2.1 提交订单意图"],
    l4: ["GET /families/{id}/commerce/customer-projection", "POST /families/{id}/commerce/order-intents"],
    capabilityState: "FROZEN",
    layoutMode: "DETAIL",
    actionPolicy: "CONTROLLED_INTENT",
  },
  "UI-15": {
    uiId: "UI-15",
    l1: "3 GROWTH 成长成果",
    l2: ["3.4 流程事件记录"],
    l3: ["3.4.1 交互事件写入"],
    l4: ["POST /families/{id}/dev/flow-events"],
    capabilityState: "SYNTHETIC_ONLY",
    layoutMode: "PRIVATE_DRAFT",
    actionPolicy: "SAVE_PRIVATE_DRAFT",
  },
  "UI-16": {
    uiId: "UI-16",
    l1: "3 GROWTH 成长成果",
    l2: ["3.4 流程事件记录"],
    l3: ["3.4.1 交互事件写入"],
    l4: ["POST /families/{id}/dev/flow-events"],
    capabilityState: "SYNTHETIC_ONLY",
    layoutMode: "PRIVATE_DRAFT",
    actionPolicy: "SAVE_PRIVATE_DRAFT",
  },
  "UI-17": {
    uiId: "UI-17",
    l1: "5 COMMERCE 商业化",
    l2: ["5.3 会员体系", "5.4 积分体系"],
    l3: ["5.4.1 积分余额", "5.4.2 积分兑换"],
    l4: ["No production ledger or redemption endpoint"],
    capabilityState: "GATE_BOUNDARY",
    layoutMode: "BOUNDARY",
    actionPolicy: "NO_VALUE_MUTATION",
  },
  "UI-18": {
    uiId: "UI-18",
    l1: "5 COMMERCE 商业化",
    l2: ["5.3 会员体系", "5.5 会员界面投影"],
    l3: ["5.3.1 会员方案查询", "5.3.2 会员投影", "5.5 会员界面投影"],
    l4: [
      "GET /families/{id}/membership/plans",
      "GET /families/{id}/membership/customer-projection",
      "GET /projection",
      "GET /screens/{surface_id}",
    ],
    capabilityState: "READ_ONLY",
    layoutMode: "READ_ONLY",
    actionPolicy: "READ_ONLY",
  },
} as const satisfies Record<string, UiFunctionalHierarchy>;

export const ACTIVITY_UI_FUNCTIONAL_HIERARCHY = {
  "UI-22": {
    uiId: "UI-22",
    l1: "3 GROWTH 成长成果",
    l2: ["3.1 成长活动目录"],
    l3: ["3.1.1 平台界面投影", "3.1.2 活动卡片文案"],
    l4: ["GET /families/{id}/dev/platform-surfaces"],
    capabilityState: "SYNTHETIC_ONLY",
    layoutMode: "CATALOG",
    actionPolicy: "NAVIGATE_ONLY",
  },
  "UI-23": {
    uiId: "UI-23",
    l1: "3 GROWTH 成长成果",
    l2: ["3.4 流程事件记录"],
    l3: ["3.4.1 交互事件写入"],
    l4: ["POST /families/{id}/dev/flow-events"],
    capabilityState: "SYNTHETIC_ONLY",
    layoutMode: "PRIVATE_DRAFT",
    actionPolicy: "SAVE_PRIVATE_DRAFT",
  },
} as const satisfies Record<string, UiFunctionalHierarchy>;

export function getCommerceUiFunctionalHierarchy(uiId: keyof typeof COMMERCE_UI_FUNCTIONAL_HIERARCHY) {
  return COMMERCE_UI_FUNCTIONAL_HIERARCHY[uiId];
}

export function getActivityUiFunctionalHierarchy(uiId: keyof typeof ACTIVITY_UI_FUNCTIONAL_HIERARCHY) {
  return ACTIVITY_UI_FUNCTIONAL_HIERARCHY[uiId];
}
