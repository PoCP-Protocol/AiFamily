import { FamilyApiError } from "../../lib/family/family-api-client";
import type { FamilyApiCommerceProduct } from "../../lib/family/family-api-projections";

export type CatalogProduct = {
  ref: string;
  title: string;
  summary: string;
  category: "COURSE" | "ASSESSMENT" | "TOOL";
  delivery: string[];
  provenance: "REMOTE" | "SYNTHETIC";
  accent: string;
};

export function mapRemoteProducts(products: readonly FamilyApiCommerceProduct[] | undefined): CatalogProduct[] {
  return (products ?? []).map((product, index) => {
    const attrs = product.attributes ?? {};
    return {
      ref: product.product_ref,
      title: product.title,
      summary: stringAttribute(attrs.subtitle, "从家庭当前需要出发，先了解支持方向。"),
      category: categoryAttribute(attrs.category),
      delivery: stringArrayAttribute(attrs.delivery, ["家庭说明", "下一步行动"]),
      provenance: "REMOTE",
      accent: index % 2 === 0 ? "#2563EB" : "#F28C45",
    };
  });
}

export function classifyCatalogError(error: unknown): "denied" | "error" {
  if (error instanceof FamilyApiError && (error.status === 401 || error.status === 403 || error.code.includes("CONSENT") || error.code.includes("POLICY"))) return "denied";
  return "error";
}

function stringAttribute(value: unknown, fallback: string) {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function stringArrayAttribute(value: unknown, fallback: string[]) {
  return Array.isArray(value) && value.every((item) => typeof item === "string") ? value as string[] : fallback;
}

function categoryAttribute(value: unknown): CatalogProduct["category"] {
  return value === "COURSE" || value === "ASSESSMENT" || value === "TOOL" ? value : "TOOL";
}
