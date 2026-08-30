import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { FamilyApiError } from "../lib/family/family-api-client";
import { classifyCatalogError, mapRemoteProducts } from "../app/catalog/catalog-contract";
import { mapServiceOfferings } from "../app/services/service-contract";

const source = (path: string) => readFileSync(resolve(__dirname, path), "utf8");

describe("S1-C family need -> service/product -> plan journey", () => {
  it("maps only server-owned products and services into the discovery cards", () => {
    const products = mapRemoteProducts([{
      product_id: "product-1",
      product_ref: "PRODUCT_REMOTE_1",
      product_version: 3,
      title: "家庭对话支持",
      admission_status: "ADMITTED",
      source_ref: "catalog-v3",
      fixture_only: true,
      attributes_schema_version: 1,
      attributes: { subtitle: "从一个具体时刻开始", delivery: ["行动卡", "回看"] },
    }]);
    const services = mapServiceOfferings([{
      service_offering_id: "service-1",
      service_offering_ref: "SERVICE_REMOTE_1",
      version_no: 2,
      title: "家庭支持服务",
      provider_id: "provider-1",
      provider_display_name: "支持团队",
      provider_kind: "TEAM",
      channel_options: ["TEXT"],
      open_slot_count: 0,
    }]);
    expect(products[0]).toMatchObject({ ref: "PRODUCT_REMOTE_1", provenance: "REMOTE", summary: "从一个具体时刻开始" });
    expect(services[0]).toMatchObject({ ref: "SERVICE_REMOTE_1", provenance: "REMOTE", provider: "支持团队" });
    expect(source("../app/catalog/catalog-experience.tsx")).toContain("家庭需要");
    expect(source("../app/services/service-experience.tsx")).toContain("服务端");
  });

  it("keeps explicit loading/empty/denied/error and synthetic environment states", () => {
    expect(classifyCatalogError(new FamilyApiError("denied", 403, "CONSENT_REQUIRED", null))).toBe("denied");
    expect(classifyCatalogError(new FamilyApiError("broken", 500, "UPSTREAM_ERROR", null))).toBe("error");
    const catalog = source("../app/catalog/catalog-experience.tsx");
    const services = source("../app/services/service-experience.tsx");
    for (const state of ["loading", "empty", "denied", "error", "synthetic"]) {
      expect(catalog).toContain(`loadState === "${state}"`);
      expect(services).toContain(`state === "${state}"`);
    }
    expect(catalog).toContain("createSyntheticMultimodalAdapter");
    expect(catalog).toContain("CONSENT_REQUIRED");
    expect(catalog).toContain("UPLOAD_FAILED");
  });

  it("preserves emotional-first, no-ranking and draft-only boundaries", () => {
    const catalog = source("../app/catalog/catalog-experience.tsx");
    const product = source("../app/catalog/products/product-detail-experience.tsx");
    const services = source("../app/services/service-experience.tsx");
    for (const text of ["先接住", "小行动", "方案草案", "不展示家庭总分、排名或比较"]) expect(catalog).toContain(text);
    for (const text of ["不需要马上变得更好", "方案草案", "不扣款", "不自动开通"]) expect(product).toContain(text);
    for (const text of ["先接住疲惫", "方案草案", "不展示家庭总分或排名"]) expect(services).toContain(text);
    expect(product).toContain('attributes: { entry: "family-needs-catalog", intent: "PLAN_DRAFT" }');
    expect(product).not.toMatch(/立即购买|checkout|paymentIntent/);
  });

  it("wires semantic resource routes without removing legacy UI baselines", () => {
    expect(source("../app/catalog/index.tsx")).toContain("./catalog-experience");
    expect(source("../app/catalog/products/index.tsx")).toContain('mode="products"');
    expect(source("../app/catalog/products/[productRef].tsx")).toContain("product-detail-experience");
    expect(source("../app/services/offerings/[offeringRef].tsx")).toContain("ServiceOfferingDetailExperienceScreen");
    expect(source("../app/services/overview.tsx")).toContain("service-experience");
  });
});
