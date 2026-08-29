export interface FamilyApiChildActionPrompt {
  state: "ACTION_RECORDED";
  focus: string;
  headline: string;
  shared_action: string;
  pause_hint: string;
  action_route: "growth-daily-task";
  fact_boundary: "ACTION_RECORDED_NOT_CHILD_OUTCOME";
}

export interface FamilyApiCoreGrowthProjection {
  projection_version: "DEV_CORE_GROWTH_V1";
  family_id: string;
  data_source: "SYNTHETIC_DEV_ONLY";
  model_gateway: {
    status: "NOOP_NOT_INVOKED";
    rule: "NO_FREE_TEXT_MODEL_WRITE_TO_CORE_ONTOLOGY";
  };
  cards: readonly {
    surface: string;
    child_action_prompt?: FamilyApiChildActionPrompt;
  }[];
}

export interface FamilyApiPersonalGrowthJourney {
  state: "STARTING" | "IN_PROGRESS";
  headline: string;
  entries: readonly { event_id: string; label: string; detail: string }[];
  fact_boundary: "PROCESS_EVENTS_NOT_OUTCOME_OR_RANKING";
}

export interface FamilyApiPrivateGrowthStory {
  state: "WAITING_FOR_MOMENT" | "READY";
  title: string;
  summary: string;
  moments: readonly string[];
  fact_boundary: "PROCESS_EVENTS_NOT_OUTCOME_OR_SHARE";
}

export interface FamilyApiGrowthActivity {
  activity_ref: string;
  title: string;
  summary: string;
  age_hint: string;
  detail_route: "activity-detail";
}

export interface FamilyApiGrowthActivityCatalog {
  state: "READY";
  headline: string;
  introduction: string;
  activities: readonly FamilyApiGrowthActivity[];
  support_topics_route: "teacher-zone";
  fact_boundary: "ACTIVITY_BROWSING_NOT_REGISTRATION_ATTENDANCE_OR_OUTCOME";
}

export interface FamilyApiLearningExchangeEntry {
  exchange_ref: string;
  title: string;
  summary: string;
  topic: string;
  detail_route: "dynamic-detail";
}

export interface FamilyApiLearningExchangeFeed {
  state: "READY";
  headline: string;
  introduction: string;
  entries: readonly FamilyApiLearningExchangeEntry[];
  activity_catalog_route: "salon-list";
  fact_boundary: "READING_EXPERIENCE_SUMMARIES_NOT_PUBLICATION_INTERACTION_OR_OUTCOME";
}

export interface FamilyApiPlatformSurfacesProjection {
  projection_version: "DEV_PLATFORM_SURFACES_V1";
  family_id: string;
  data_source: "SYNTHETIC_DEV_ONLY";
  external_effect_adapter: "NOOP_NOT_INVOKED";
  model_gateway: "NOOP_NOT_INVOKED";
  cards: readonly {
    surface: string;
    personal_growth_journey?: FamilyApiPersonalGrowthJourney;
    private_growth_story?: FamilyApiPrivateGrowthStory;
    family_growth_activity_catalog?: FamilyApiGrowthActivityCatalog;
    family_learning_exchange_feed?: FamilyApiLearningExchangeFeed;
  }[];
}

export interface FamilyApiServiceOffering {
  service_offering_id: string;
  service_offering_ref: string;
  version_no: number;
  title: string;
  provider_ref: string;
  provider_display_name: string;
  provider_kind: "TEACHER";
  qualification_status: "ACTIVE";
  admission_status: "ADMITTED";
  offering_status: "ACTIVE";
  service_type: string | null;
  age_band: string | null;
  next_available_at: string | null;
  next_available_channel: "VIDEO" | "TEXT" | "OFFLINE" | null;
  availability_status: "AVAILABLE" | "UNAVAILABLE";
  fixture_only: true;
  attributes_schema_version: number;
}

export interface FamilyApiExpertLiveSession {
  session_ref: string;
  title: string;
  topic: string;
  starts_at: string;
  status: "SCHEDULED" | "LIVE" | "ENDED";
  host_display_name: string;
  fixture_only: true;
  external_effect: false;
}

export interface FamilyApiServiceSupplyProjection {
  family_id: string;
  source_page_id: "UI-19";
  projection_version: number;
  as_of: string;
  visibility: "FAMILY_SCOPED_ADMITTED_SUPPLY";
  external_effect: false;
  offerings: FamilyApiServiceOffering[];
  live_session: FamilyApiExpertLiveSession | null;
  text_equivalent: string;
}

export interface FamilyApiAvailabilitySlot {
  availability_slot_id: string;
  availability_slot_ref: string;
  service_offering_ref: string;
  starts_at: string;
  ends_at: string;
  channel: "VIDEO" | "TEXT" | "OFFLINE";
  status: "AVAILABLE" | "RESERVED";
}

export interface FamilyApiServiceSlotsProjection {
  tenant_id: string;
  slots: FamilyApiAvailabilitySlot[];
}

export interface FamilyApiServiceBookingReceipt {
  booking: {
    booking_request_id: string;
    booking_ref: string;
    status: "DRAFT" | "REQUESTED" | "CONFIRMED" | "CANCELLED" | "EXPIRED" | "REPLAYED";
    service_offering_ref: string;
    availability_slot_ref: string;
    row_version: number;
    event_id: string;
    external_effect: false;
    environment: "DEV" | "TEST";
    text_equivalent: string;
  };
  service_record: {
    service_record_id: string;
    status: "PENDING" | "SCHEDULED" | "CANCELLED" | "COMPLETED";
    source_booking_request_id: string;
    projection_version: number;
    external_effect: false;
    text_equivalent: string;
  };
}

export interface FamilyApiServiceCustomerProjection {
  family_id: string;
  projection_version: number;
  as_of: string;
  visibility: "FAMILY_PRIVATE";
  bookings: readonly {
    booking_request_id: string;
    booking_ref: string;
    status: "DRAFT" | "REQUESTED" | "CONFIRMED" | "CANCELLED" | "EXPIRED";
    service_offering_ref: string;
    availability_slot_ref: string;
    starts_at: string;
    channel: "VIDEO" | "TEXT" | "OFFLINE";
  }[];
  service_records: readonly {
    service_record_id: string;
    source_booking_request_id: string;
    status: "PENDING" | "SCHEDULED" | "CANCELLED" | "COMPLETED";
  }[];
  text_equivalent: string;
}

export interface FamilyApiCommerceProduct {
  product_id: string;
  product_ref: string;
  product_version: number;
  title: string;
  admission_status: "ADMITTED";
  source_ref: string;
  fixture_only: true;
  attributes_schema_version: number;
}

export interface FamilyApiCommerceProductsProjection {
  tenant_id: string;
  products: FamilyApiCommerceProduct[];
}

export interface FamilyApiCommerceIntentReceipt {
  intent: {
    order_intent_id: string;
    intent_ref: string;
    status: "DRAFT" | "SUBMITTED" | "CANCELLED" | "EXPIRED";
    product_ref: string;
    product_version: number;
    row_version: number;
    external_effect: false;
    environment: "DEV" | "TEST";
    text_equivalent: string;
  };
  entitlement: {
    entitlement_id: string;
    entitlement_ref: string;
    status: "PENDING" | "AVAILABLE" | "REVOKED" | "EXPIRED";
    source_order_intent_id: string;
    external_effect: false;
    text_equivalent: string;
  };
}

export interface FamilyApiCommerceCustomerProjection {
  family_id: string;
  projection_version: number;
  visibility: "FAMILY_PRIVATE";
  order_intents: readonly {
    order_intent_id: string;
    status: "DRAFT" | "SUBMITTED" | "CANCELLED" | "EXPIRED";
    product_ref: string;
    product_version: number;
    created_at: string;
  }[];
  entitlements: readonly {
    entitlement_id: string;
    status: "PENDING" | "AVAILABLE" | "REVOKED" | "EXPIRED";
    source_order_intent_id: string;
    available_at: string | null;
    expires_at: string | null;
  }[];
  text_equivalent: string;
}

export interface FamilyApiMembershipPlan {
  plan_id: string;
  plan_ref: string;
  version_no: number;
  title: string;
  status: "ACTIVE";
  effective_from: string;
  effective_to: string | null;
  fixture_only: true;
  benefits: readonly {
    benefit_definition_id: string;
    benefit_ref: string;
    title: string;
    allocation_type: "COUNT" | "ACCESS" | "CREDIT";
    units_per_grant: number;
    valid_days: number | null;
  }[];
}

export interface FamilyApiMembershipPlansProjection {
  tenant_id: string;
  plans: FamilyApiMembershipPlan[];
}

export interface FamilyApiMembershipProjection {
  family_id: string;
  projection_version: number;
  visibility: "FAMILY_PRIVATE";
  subscriptions: readonly {
    membership_subscription_id: string;
    plan_ref: string;
    plan_version: number;
    status: "PENDING" | "ACTIVE" | "PAUSED" | "EXPIRED" | "CANCELLED";
    effective_from: string;
    effective_to: string | null;
  }[];
  benefits: readonly {
    benefit_grant_id: string;
    benefit_ref: string;
    status: "PENDING" | "AVAILABLE" | "CONSUMED" | "REVOKED" | "EXPIRED";
    allocated_units: number;
    remaining_units: number;
    valid_from: string;
    valid_to: string | null;
  }[];
  dev_points?: {
    balance: number;
    source: "DEV_FIXTURE";
    redeemable: false;
  };
  text_equivalent: string;
}

export function selectChildActionPrompt(projection: FamilyApiCoreGrowthProjection | null) {
  return projection?.cards.find((card) => card.surface === "UI-10")?.child_action_prompt ?? null;
}

export function selectPersonalGrowthJourney(projection: FamilyApiPlatformSurfacesProjection | null) {
  return projection?.cards.find((card) => card.surface === "UI-11")?.personal_growth_journey ?? null;
}

export function selectPrivateGrowthStory(projection: FamilyApiPlatformSurfacesProjection | null) {
  return projection?.cards.find((card) => card.surface === "UI-12")?.private_growth_story ?? null;
}

export function selectGrowthActivityCatalog(projection: FamilyApiPlatformSurfacesProjection | null) {
  return projection?.cards.find((card) => card.surface === "UI-22")?.family_growth_activity_catalog ?? null;
}

export function selectLearningExchangeFeed(projection: FamilyApiPlatformSurfacesProjection | null) {
  return projection?.cards.find((card) => card.surface === "UI-25")?.family_learning_exchange_feed ?? null;
}

export function selectLearningExchangeEntry(projection: FamilyApiPlatformSurfacesProjection | null, exchangeRef?: string | null) {
  const feed = selectLearningExchangeFeed(projection);
  return feed?.entries.find((entry) => entry.exchange_ref === exchangeRef) ?? feed?.entries[0] ?? null;
}
