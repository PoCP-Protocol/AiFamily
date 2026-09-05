import { describe, expect, it } from "vitest";

import {
  ASSESSMENT_LEGACY_ROUTE_MAP,
  ASSESSMENT_ROUTES,
  COMMUNITY_LEGACY_ROUTE_MAP,
  COMMUNITY_ROUTES,
  COMMERCE_LEGACY_ROUTE_MAP,
  COMMERCE_ROUTES,
  FAMILY_LEGACY_ROUTE_MAP,
  FAMILY_ROUTES,
  GROWTH_LEGACY_ROUTE_MAP,
  GROWTH_ROUTES,
  HOME_LEGACY_ROUTE_MAP,
  HOME_ROUTES,
  JOURNEY_LEGACY_ROUTE_MAP,
  JOURNEY_ROUTES,
  SERVICE_LEGACY_ROUTE_MAP,
  SERVICE_ROUTES,
  SEMANTIC_UI_ROUTE_MAP,
  activityRoute,
  bookingRoute,
  communityExchangeRoute,
  offeringRoute,
  productRoute,
  routeForUi,
  uiIdForPathname,
} from "../lib/navigation/family-routes";

describe("semantic mobile routes", () => {
  it("maps the assessment UI identifiers to stable business routes", () => {
    expect(ASSESSMENT_LEGACY_ROUTE_MAP).toEqual({
      "UI-02": "/assessment/session",
      "UI-02-result": "/assessment/result",
      "UI-03": "/assessment/interpretation",
      "UI-07": "/assessment",
    });
    expect(new Set(Object.values(ASSESSMENT_ROUTES)).size).toBe(4);
  });

  it("maps the plan and action UI identifiers to journey routes", () => {
    expect(JOURNEY_LEGACY_ROUTE_MAP).toEqual({
      "UI-04": "/journeys/plan",
      "UI-05": "/journeys/current",
      "UI-08": "/journeys/review",
      "UI-09": "/actions/today",
    });
    expect(new Set(Object.values(JOURNEY_ROUTES)).size).toBe(4);
  });

  it("keeps every migrated UI identifier and semantic route unique", () => {
    expect(Object.keys(SEMANTIC_UI_ROUTE_MAP)).toHaveLength(35);
    expect(new Set(Object.values(SEMANTIC_UI_ROUTE_MAP)).size).toBe(35);
  });

  it("maps commerce, membership, invite and asset screens by business meaning", () => {
    expect(COMMERCE_LEGACY_ROUTE_MAP).toEqual({
      "UI-06": "/membership/benefits",
      "UI-13": "/catalog",
      "UI-14": "/catalog/products",
      "UI-15": "/invites/new",
      "UI-16": "/group-plans",
      "UI-17": "/rewards/points",
      "UI-18": "/membership",
      "UI-30": "/membership/annual-plan",
      "UI-32": "/assets",
    });
    expect(new Set(Object.values(COMMERCE_ROUTES)).size).toBe(9);
  });

  it("builds a typed product resource route without a query-string cast", () => {
    expect(productRoute("PRODUCT_PARENT_CHILD_CAMP")).toEqual({
      pathname: "/catalog/products/[productRef]",
      params: { productRef: "PRODUCT_PARENT_CHILD_CAMP" },
    });
  });

  it("maps service and activity screens to stable capability routes", () => {
    expect(SERVICE_LEGACY_ROUTE_MAP).toEqual({
      "UI-19": "/services/offerings",
      "UI-20": "/services/offerings/detail",
      "UI-21": "/services/bookings/new",
      "UI-22": "/activities",
      "UI-23": "/activities/detail",
      "UI-24": "/services/bookings",
      "UI-31": "/services/overview",
      "UI-34": "/services/records",
    });
    expect(new Set(Object.values(SERVICE_ROUTES)).size).toBe(8);
  });

  it("builds typed service resource routes and preserves booking context", () => {
    expect(offeringRoute("OFFERING_PARENT_COACHING")).toEqual({
      pathname: "/services/offerings/[offeringRef]",
      params: { offeringRef: "OFFERING_PARENT_COACHING" },
    });
    expect(bookingRoute("OFFERING_PARENT_COACHING", "SLOT_WEEKEND_AM")).toEqual({
      pathname: "/services/bookings/new",
      params: {
        offeringRef: "OFFERING_PARENT_COACHING",
        slotRef: "SLOT_WEEKEND_AM",
      },
    });
    expect(activityRoute("ACTIVITY_FAMILY_DIALOGUE")).toEqual({
      pathname: "/activities/[activityRef]",
      params: { activityRef: "ACTIVITY_FAMILY_DIALOGUE" },
    });
  });

  it("maps the home, growth and family profile screens by user purpose", () => {
    expect(HOME_LEGACY_ROUTE_MAP).toEqual({ "UI-01": "/" });
    expect(GROWTH_LEGACY_ROUTE_MAP).toEqual({
      "UI-10": "/growth/child-assistant",
      "UI-11": "/growth/rhythm",
      "UI-12": "/growth/story",
      "UI-29": "/growth/outcomes",
    });
    expect(FAMILY_LEGACY_ROUTE_MAP).toEqual({ "UI-33": "/family/profile" });
    expect(new Set(Object.values(HOME_ROUTES)).size).toBe(1);
    expect(new Set(Object.values(GROWTH_ROUTES)).size).toBe(4);
    expect(new Set(Object.values(FAMILY_ROUTES)).size).toBe(1);
  });

  it("maps community screens without presenting private drafts as published content", () => {
    expect(COMMUNITY_LEGACY_ROUTE_MAP).toEqual({
      "UI-25": "/community",
      "UI-26": "/community/notes/new",
      "UI-27": "/community/exchanges/detail",
      "UI-28": "/community/mine",
    });
    expect(new Set(Object.values(COMMUNITY_ROUTES)).size).toBe(4);
  });

  it("builds a typed community exchange resource route", () => {
    expect(communityExchangeRoute("EXCHANGE_DIALOGUE_PAUSE")).toEqual({
      pathname: "/community/exchanges/[exchangeRef]",
      params: { exchangeRef: "EXCHANGE_DIALOGUE_PAUSE" },
    });
  });

  it("keeps an explicit compatibility fallback for domains not migrated yet", () => {
    expect(routeForUi("UI-07")).toBe("/assessment");
    expect(routeForUi("UI-04")).toBe("/journeys/plan");
    expect(routeForUi("UI-01")).toBe("/");
    expect(routeForUi("UI-99")).toBe("/ui/UI-99");
  });

  it("resolves both semantic and legacy pathnames back to their UI traceability id", () => {
    expect(uiIdForPathname("/growth/outcomes")).toBe("UI-29");
    expect(uiIdForPathname("/ui/UI-29")).toBe("UI-29");
    expect(uiIdForPathname("/not-a-family-route")).toBeUndefined();
  });
});
