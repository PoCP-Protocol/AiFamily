import type { FamilyApiCommerceProduct } from "./family-api-projections";

export type CommerceCategory = "COURSE" | "ASSESSMENT" | "TOOL";

export interface CommercePresentationProduct {
  productRef: string;
  productVersion: number;
  title: string;
  subtitle: string;
  category: CommerceCategory;
  audience: string;
  delivery: readonly string[];
  listPriceLabel: string;
  familyPriceLabel: string;
  memberPriceLabel: string;
  heroTag?: string;
  priceMain?: string;
  priceOriginal?: string;
  priceGroup?: string;
  priceMember?: string;
  assurances?: readonly string[];
  accent: string;
  source: "FAMILY_API" | "EXISTING_WEB_BASELINE_PRESENTATION";
  fixtureOnly: true;
}

/**
 * Presentation-only metadata inherited from the existing Web commerce baseline.
 * Product identity, version and admission still come from Family API whenever it is connected.
 */
export const EXISTING_COMMERCE_PRESENTATION: readonly CommercePresentationProduct[] = [
  {
    productRef: "PRODUCT_PARENT_CHILD_CAMP",
    productVersion: 1,
    title: "21天亲子沟通挑战营",
    subtitle: "改善亲子关系，从有效沟通开始",
    category: "COURSE",
    audience: "希望改善日常亲子沟通节奏的家庭",
    delivery: ["视频课程", "每日打卡", "社群交流", "专家答疑"],
    listPriceLabel: "原方案 ¥699",
    familyPriceLabel: "同行意向 ¥399",
    memberPriceLabel: "会员意向 ¥179",
    heroTag: "家庭成长好物",
    priceMain: "¥399",
    priceOriginal: "原价¥699",
    priceGroup: "拼团价 ¥199 (3人成团)",
    priceMember: "会员价 ¥179 (会员再享95折)",
    assurances: ["21天系统训练", "打卡社群陪伴", "专家顾问答疑"],
    accent: "#2563EB",
    source: "EXISTING_WEB_BASELINE_PRESENTATION",
    fixtureOnly: true,
  },
  {
    productRef: "PRODUCT_FAMILY_ASSESSMENT_CARD",
    productVersion: 1,
    title: "家庭成长测评卡",
    subtitle: "从真实家庭场景开始了解关注方向",
    category: "ASSESSMENT",
    audience: "想从一个具体场景开始梳理的家庭",
    delivery: ["场景测评", "家庭说明", "关注方向", "下一步建议"],
    listPriceLabel: "方案参考 ¥59",
    familyPriceLabel: "家庭意向 ¥39",
    memberPriceLabel: "会员权益可查看",
    accent: "#16866D",
    source: "EXISTING_WEB_BASELINE_PRESENTATION",
    fixtureOnly: true,
  },
  {
    productRef: "PRODUCT_PARENT_CHILD_READING_TOOLKIT",
    productVersion: 1,
    title: "亲子阅读工具包",
    subtitle: "把共读变成低负担的家庭时光",
    category: "TOOL",
    audience: "希望建立轻松共读节奏的家庭",
    delivery: ["共读卡", "提问卡", "记录页", "家庭小结"],
    listPriceLabel: "方案参考 ¥99",
    familyPriceLabel: "家庭意向 ¥69",
    memberPriceLabel: "会员权益可查看",
    accent: "#F28C45",
    source: "EXISTING_WEB_BASELINE_PRESENTATION",
    fixtureOnly: true,
  },
  {
    productRef: "PRODUCT_FAMILY_FOCUS_CAMP",
    productVersion: 1,
    title: "家庭专注力提升训练营",
    subtitle: "从环境支持和家庭节奏开始练习",
    category: "COURSE",
    audience: "希望减少催促、建立可持续日常节奏的家庭",
    delivery: ["家庭说明", "环境清单", "行动练习", "阶段回看"],
    listPriceLabel: "方案参考 ¥399",
    familyPriceLabel: "同行意向 ¥199",
    memberPriceLabel: "会员权益可查看",
    accent: "#7556C8",
    source: "EXISTING_WEB_BASELINE_PRESENTATION",
    fixtureOnly: true,
  },
] as const;

export function commerceProductsForDisplay(remoteProducts: readonly FamilyApiCommerceProduct[] | undefined) {
  if (!remoteProducts?.length) return EXISTING_COMMERCE_PRESENTATION;
  const remoteByRef = new Map(remoteProducts.map((product) => [product.product_ref, product]));
  const inheritedProducts = EXISTING_COMMERCE_PRESENTATION.map((inherited) => {
    const product = remoteByRef.get(inherited.productRef);
    if (!product) return inherited;
    return {
      ...inherited,
      productRef: product.product_ref,
      productVersion: product.product_version,
      title: product.title,
      source: "FAMILY_API" as const,
      fixtureOnly: product.fixture_only,
    };
  });
  const inheritedRefs = new Set(inheritedProducts.map((item) => item.productRef));
  const additionalProducts = remoteProducts
    .filter((product) => !inheritedRefs.has(product.product_ref))
    .map((product, index) => ({
      ...EXISTING_COMMERCE_PRESENTATION[index % EXISTING_COMMERCE_PRESENTATION.length],
      productRef: product.product_ref,
      productVersion: product.product_version,
      title: product.title,
      source: "FAMILY_API" as const,
      fixtureOnly: product.fixture_only,
    }));
  return [...inheritedProducts, ...additionalProducts];
}

export interface CommerceIntentDraft {
  id: string;
  productRef: string;
  productVersion: number;
  productTitle: string;
  state: "LOCAL_DRAFT" | "SYNCED_RECEIPT";
  intentId: string | null;
  entitlementId: string | null;
  visibility: "FAMILY_PRIVATE";
  externalEffect: false;
  recordedAt: string;
}

export interface FamilyInvitationDraft {
  id: string;
  productRef: string;
  productTitle: string;
  state: "PRIVATE_DRAFT";
  visibility: "FAMILY_PRIVATE";
  externalEffect: false;
  recordedAt: string;
}

export interface FamilyStudyGroupDraft {
  id: string;
  productRef: string;
  productTitle: string;
  familyCount: 2 | 3 | 4;
  state: "PRIVATE_DRAFT" | "CANCELLED";
  visibility: "FAMILY_PRIVATE";
  externalEffect: false;
  recordedAt: string;
}
