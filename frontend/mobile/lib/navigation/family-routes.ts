import type { Href } from "expo-router";

export const HOME_ROUTES = {
  home: "/",
} as const satisfies Record<string, Href>;

export type HomeLegacyUiId = "UI-01";

export const HOME_LEGACY_ROUTE_MAP = {
  "UI-01": HOME_ROUTES.home,
} as const satisfies Record<HomeLegacyUiId, Href>;

export const ASSESSMENT_ROUTES = {
  overview: "/assessment",
  session: "/assessment/session",
  result: "/assessment/result",
  interpretation: "/assessment/interpretation",
} as const satisfies Record<string, Href>;

export type AssessmentLegacyUiId = "UI-02" | "UI-02-result" | "UI-03" | "UI-07";

export const ASSESSMENT_LEGACY_ROUTE_MAP = {
  "UI-02": ASSESSMENT_ROUTES.session,
  "UI-02-result": ASSESSMENT_ROUTES.result,
  "UI-03": ASSESSMENT_ROUTES.interpretation,
  "UI-07": ASSESSMENT_ROUTES.overview,
} as const satisfies Record<AssessmentLegacyUiId, Href>;

export const JOURNEY_ROUTES = {
  plan: "/journeys/plan",
  current: "/journeys/current",
  review: "/journeys/review",
  todayAction: "/actions/today",
} as const satisfies Record<string, Href>;

export type JourneyLegacyUiId = "UI-04" | "UI-05" | "UI-08" | "UI-09";

export const JOURNEY_LEGACY_ROUTE_MAP = {
  "UI-04": JOURNEY_ROUTES.plan,
  "UI-05": JOURNEY_ROUTES.current,
  "UI-08": JOURNEY_ROUTES.review,
  "UI-09": JOURNEY_ROUTES.todayAction,
} as const satisfies Record<JourneyLegacyUiId, Href>;

export const COMMERCE_ROUTES = {
  catalog: "/catalog",
  product: "/catalog/products",
  invite: "/invites/new",
  groupPlans: "/group-plans",
  points: "/rewards/points",
  membership: "/membership",
  membershipBenefits: "/membership/benefits",
  annualPlan: "/membership/annual-plan",
  assets: "/assets",
} as const satisfies Record<string, Href>;

export type CommerceLegacyUiId =
  | "UI-06"
  | "UI-13"
  | "UI-14"
  | "UI-15"
  | "UI-16"
  | "UI-17"
  | "UI-18"
  | "UI-30"
  | "UI-32";

export const COMMERCE_LEGACY_ROUTE_MAP = {
  "UI-06": COMMERCE_ROUTES.membershipBenefits,
  "UI-13": COMMERCE_ROUTES.catalog,
  "UI-14": COMMERCE_ROUTES.product,
  "UI-15": COMMERCE_ROUTES.invite,
  "UI-16": COMMERCE_ROUTES.groupPlans,
  "UI-17": COMMERCE_ROUTES.points,
  "UI-18": COMMERCE_ROUTES.membership,
  "UI-30": COMMERCE_ROUTES.annualPlan,
  "UI-32": COMMERCE_ROUTES.assets,
} as const satisfies Record<CommerceLegacyUiId, Href>;

export const SERVICE_ROUTES = {
  overview: "/services/overview",
  offerings: "/services/offerings",
  offeringDetail: "/services/offerings/detail",
  booking: "/services/bookings/new",
  bookings: "/services/bookings",
  records: "/services/records",
  activities: "/activities",
  activityDetail: "/activities/detail",
} as const satisfies Record<string, Href>;

export type ServiceLegacyUiId =
  | "UI-19"
  | "UI-20"
  | "UI-21"
  | "UI-22"
  | "UI-23"
  | "UI-24"
  | "UI-31"
  | "UI-34";

export const SERVICE_LEGACY_ROUTE_MAP = {
  "UI-19": SERVICE_ROUTES.offerings,
  "UI-20": SERVICE_ROUTES.offeringDetail,
  "UI-21": SERVICE_ROUTES.booking,
  "UI-22": SERVICE_ROUTES.activities,
  "UI-23": SERVICE_ROUTES.activityDetail,
  "UI-24": SERVICE_ROUTES.bookings,
  "UI-31": SERVICE_ROUTES.overview,
  "UI-34": SERVICE_ROUTES.records,
} as const satisfies Record<ServiceLegacyUiId, Href>;

export const GROWTH_ROUTES = {
  childAssistant: "/growth/child-assistant",
  rhythm: "/growth/rhythm",
  story: "/growth/story",
  outcomes: "/growth/outcomes",
} as const satisfies Record<string, Href>;

export type GrowthLegacyUiId = "UI-10" | "UI-11" | "UI-12" | "UI-29";

export const GROWTH_LEGACY_ROUTE_MAP = {
  "UI-10": GROWTH_ROUTES.childAssistant,
  "UI-11": GROWTH_ROUTES.rhythm,
  "UI-12": GROWTH_ROUTES.story,
  "UI-29": GROWTH_ROUTES.outcomes,
} as const satisfies Record<GrowthLegacyUiId, Href>;

export const COMMUNITY_ROUTES = {
  feed: "/community",
  newNote: "/community/notes/new",
  exchangeDetail: "/community/exchanges/detail",
  mine: "/community/mine",
} as const satisfies Record<string, Href>;

export type CommunityLegacyUiId = "UI-25" | "UI-26" | "UI-27" | "UI-28";

export const COMMUNITY_LEGACY_ROUTE_MAP = {
  "UI-25": COMMUNITY_ROUTES.feed,
  "UI-26": COMMUNITY_ROUTES.newNote,
  "UI-27": COMMUNITY_ROUTES.exchangeDetail,
  "UI-28": COMMUNITY_ROUTES.mine,
} as const satisfies Record<CommunityLegacyUiId, Href>;

export const FAMILY_ROUTES = {
  profile: "/family/profile",
} as const satisfies Record<string, Href>;

export type FamilyLegacyUiId = "UI-33";

export const FAMILY_LEGACY_ROUTE_MAP = {
  "UI-33": FAMILY_ROUTES.profile,
} as const satisfies Record<FamilyLegacyUiId, Href>;

export const SEMANTIC_UI_ROUTE_MAP = {
  ...HOME_LEGACY_ROUTE_MAP,
  ...ASSESSMENT_LEGACY_ROUTE_MAP,
  ...JOURNEY_LEGACY_ROUTE_MAP,
  ...COMMERCE_LEGACY_ROUTE_MAP,
  ...SERVICE_LEGACY_ROUTE_MAP,
  ...GROWTH_LEGACY_ROUTE_MAP,
  ...COMMUNITY_LEGACY_ROUTE_MAP,
  ...FAMILY_LEGACY_ROUTE_MAP,
} as const satisfies Record<
  | HomeLegacyUiId
  | AssessmentLegacyUiId
  | JourneyLegacyUiId
  | CommerceLegacyUiId
  | ServiceLegacyUiId
  | GrowthLegacyUiId
  | CommunityLegacyUiId
  | FamilyLegacyUiId,
  Href
>;

export type SemanticUiId = keyof typeof SEMANTIC_UI_ROUTE_MAP;

export function productRoute(productRef: string): Href {
  return {
    pathname: "/catalog/products/[productRef]",
    params: { productRef },
  };
}

export function offeringRoute(offeringRef: string): Href {
  return {
    pathname: "/services/offerings/[offeringRef]",
    params: { offeringRef },
  };
}

export function bookingRoute(offeringRef?: string, slotRef?: string): Href {
  return {
    pathname: SERVICE_ROUTES.booking,
    params: {
      ...(offeringRef ? { offeringRef } : {}),
      ...(slotRef ? { slotRef } : {}),
    },
  };
}

export function activityRoute(activityRef: string): Href {
  return {
    pathname: "/activities/[activityRef]",
    params: { activityRef },
  };
}

export function communityExchangeRoute(exchangeRef: string): Href {
  return {
    pathname: "/community/exchanges/[exchangeRef]",
    params: { exchangeRef },
  };
}

export function uiIdForPathname(pathname: string): SemanticUiId | undefined {
  const semanticEntry = Object.entries(SEMANTIC_UI_ROUTE_MAP).find(([, route]) => route === pathname);
  if (semanticEntry) return semanticEntry[0] as SemanticUiId;

  const legacyMatch = /^\/ui\/(UI-\d{2}(?:-result)?)$/.exec(pathname);
  const legacyUiId = legacyMatch?.[1];
  if (legacyUiId && legacyUiId in SEMANTIC_UI_ROUTE_MAP) return legacyUiId as SemanticUiId;
  return undefined;
}

export function routeForUi(screenId: string): Href {
  const semanticRoute = SEMANTIC_UI_ROUTE_MAP[screenId as keyof typeof SEMANTIC_UI_ROUTE_MAP];
  if (semanticRoute) return semanticRoute;

  // One explicit compatibility boundary for unknown legacy UI identifiers.
  return `/ui/${screenId}` as Href;
}
