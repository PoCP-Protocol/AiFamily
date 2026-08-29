import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";

import { CAMP_21_DAYS, getCamp21Day } from "../lib/family/camp21";
import { buildFamilyRhythmEvents, buildPrivateGrowthStory, CHILD_PRACTICE_PROMPTS } from "../lib/family/child-growth";
import { commerceProductsForDisplay, EXISTING_COMMERCE_PRESENTATION } from "../lib/family/commerce-entitlements";
import { communityEntriesForDisplay, detectCommunityPrivacyRisks } from "../lib/family/community-content";
import { assessmentCompletion, GROWTH_FOCUSES } from "../lib/family/core-growth";
import { FamilyApiClient, FamilyApiError } from "../lib/family/family-api-client";
import {
  selectChildActionPrompt,
  selectGrowthActivityCatalog,
  selectLearningExchangeEntry,
  selectLearningExchangeFeed,
  selectPersonalGrowthJourney,
  selectPrivateGrowthStory,
  type FamilyApiCoreGrowthProjection,
  type FamilyApiCommerceProduct,
  type FamilyApiPlatformSurfacesProjection,
  type FamilyApiServiceOffering,
} from "../lib/family/family-api-projections";
import { familyMobileReducer, initialFamilyMobileState } from "../lib/family/family-state-core";
import { MOBILE_JOURNEY_PHASES, getJourneyWeeklyAction } from "../lib/family/journey-plan-content";
import { growthActivitiesForDisplay, serviceOfferingsForDisplay } from "../lib/family/service-support";
import { UI_ACTION_POLICIES } from "../lib/family/ui-action-policies";
import { FAMILY_SCREENS, getFamilyScreen, getScreensForTab } from "../lib/family/ui-registry";

describe("Family AI UI registry", () => {
  it("contains UI-01 through UI-34 exactly once", () => {
    const ids = FAMILY_SCREENS.map((screen) => screen.id);

    expect(ids).toHaveLength(34);
    expect(new Set(ids).size).toBe(34);
    expect(ids[0]).toBe("UI-01");
    expect(ids[ids.length - 1]).toBe("UI-34");
    expect(getFamilyScreen("UI-35")).toBeUndefined();
  });

  it("keeps home, daily task, and 90-day plan distinct", () => {
    expect(getFamilyScreen("UI-01")?.primaryTarget).toBe("UI-09");
    expect(getFamilyScreen("UI-04")?.title).toContain("90 天");
    expect(getFamilyScreen("UI-09")?.title).toBe("今日成长任务");
  });

  it("places every screen in one of the five mobile tabs", () => {
    const total = ["today", "growth", "discover", "services", "mine"]
      .map((tab) => getScreensForTab(tab as Parameters<typeof getScreensForTab>[0]).length)
      .reduce((sum, count) => sum + count, 0);

    expect(total).toBe(35);
  });

  it("keeps a named visual baseline and feature set for every baseline screen and the assessment result route", () => {
    expect(FAMILY_SCREENS.every((screen) => screen.baseline.trim().length > 0)).toBe(true);
    expect(FAMILY_SCREENS.every((screen) => screen.featurePoints.length >= 4)).toBe(true);
    expect(FAMILY_SCREENS.slice(12, 18).map((screen) => screen.baseline)).toEqual([
      "commerce-01-mall-home",
      "commerce-02-product-detail",
      "commerce-03-invite",
      "commerce-04-group-buy",
      "commerce-05-points-task",
      "commerce-06-mine-member",
    ]);
    expect(FAMILY_SCREENS.slice(18, 24).map((screen) => screen.baseline)).toEqual([
      "teacher-zone",
      "teacher-detail",
      "consultation-booking",
      "salon-list",
      "activity-detail",
      "service-mine",
    ]);
    expect(FAMILY_SCREENS.slice(24, 28).map((screen) => screen.baseline)).toEqual([
      "parent-community",
      "publish-dynamic",
      "dynamic-detail",
      "my-community",
    ]);
  });
});

describe("UI-01 to UI-34 global navigation and state readback", () => {
  it("resolves every registered primary target through an existing native route", () => {
    const mobileRoot = resolve(__dirname, "..");
    const screenFile = (id: string) => id === "UI-01"
      ? resolve(mobileRoot, "app", "(tabs)", "index.tsx")
      : resolve(mobileRoot, "app", "ui", `${id}.tsx`);

    expect(FAMILY_SCREENS).toHaveLength(34);
    for (const screen of FAMILY_SCREENS) {
      expect(existsSync(screenFile(screen.id))).toBe(true);
      expect(screen.primaryAction.trim().length).toBeGreaterThan(0);
      expect(screen.featurePoints.length).toBeGreaterThanOrEqual(4);
      if (screen.primaryTarget) {
        expect(existsSync(screenFile(screen.primaryTarget))).toBe(true);
        if (screen.primaryTarget !== "UI-02-result") {
          expect(getFamilyScreen(screen.primaryTarget)).toBeDefined();
        }
      }
    }
  });

  it("carries growth, assessment, service, commerce and community state into later readback surfaces", () => {
    const focused = familyMobileReducer(initialFamilyMobileState, { type: "select_growth_focus", focus: "PARENT_CHILD_COMMUNICATION" });
    const assessed = familyMobileReducer(focused, { type: "answer_assessment", questionId: GROWTH_FOCUSES[0].questions[0].id, answer: "sometimes" });
    const camp = familyMobileReducer(assessed, { type: "activate_camp_day", day: 1 });
    const completed = familyMobileReducer(camp, { type: "complete_action", reflection: "我先停下来听完。" });
    const service = familyMobileReducer(completed, { type: "save_consultation_need_draft", offeringRef: "TEST_PARENT_CHILD_DIALOGUE", offeringVersion: 1, offeringTitle: "亲子沟通支持", providerName: "陈老师", channel: "VIDEO", slotRef: null, timePreference: "周末上午", ageBand: "学龄", needFocus: "沟通" });
    const commerce = familyMobileReducer(service, { type: "save_commerce_intent_draft", productRef: "TEST_ANNUAL_COMPANION", productVersion: 1, productTitle: "年度陪伴" });
    const community = familyMobileReducer(commerce, { type: "save_community_post_draft", kind: "GROWTH_CHECKIN", title: "先听完的一晚", body: "我先停下来听完了。", topic: "亲子沟通", aiTagDraft: { tags: ["亲子沟通", "日常行动"], source: "MANUAL", modelGatewayStatus: "FALLBACK_RULE_BASED", factBoundary: "TAGS_ARE_EDITABLE_PERSPECTIVE_NOT_FACT" } });

    expect(community.selectedGrowthFocus).toBe("PARENT_CHILD_COMMUNICATION");
    expect(community.assessmentAnswers).toHaveProperty(GROWTH_FOCUSES[0].questions[0].id, "sometimes");
    expect(community.lastReceipt).toMatchObject({ reflectionKind: "perspective", externalEffect: false });
    expect(community.consultationNeedDraft).toMatchObject({ state: "LOCAL_DRAFT", externalEffect: false });
    expect(community.commerceIntentDraft).toMatchObject({ state: "LOCAL_DRAFT", externalEffect: false });
    expect(community.communityPostDraft).toMatchObject({ visibility: "FAMILY_PRIVATE", perspectiveKind: "PARENT_PERSPECTIVE_NOT_FACT", externalEffect: false });
    expect(community.communityPostDraft?.aiTagDraft).toMatchObject({ tags: ["亲子沟通", "日常行动"], factBoundary: "TAGS_ARE_EDITABLE_PERSPECTIVE_NOT_FACT" });
  });
});

describe("21-day parent growth camp", () => {
  it("contains 21 ordered daily practices across three seven-day stages", () => {
    expect(CAMP_21_DAYS).toHaveLength(21);
    expect(CAMP_21_DAYS.map((day) => day.day)).toEqual(Array.from({ length: 21 }, (_, index) => index + 1));
    expect(CAMP_21_DAYS.filter((day) => day.stage === "观察与连接")).toHaveLength(7);
    expect(CAMP_21_DAYS.filter((day) => day.stage === "沟通与习惯")).toHaveLength(7);
    expect(CAMP_21_DAYS.filter((day) => day.stage === "反思与延续")).toHaveLength(7);
  });

  it("clamps an invalid day into the supported range", () => {
    expect(getCamp21Day(0).day).toBe(1);
    expect(getCamp21Day(99).day).toBe(21);
  });
});

describe("Today action and camp check-in state", () => {
  it("activates the selected camp day as the shared Today action", () => {
    const state = familyMobileReducer(initialFamilyMobileState, { type: "activate_camp_day", day: 1 });

    expect(state.campStarted).toBe(true);
    expect(state.activeCampDay).toBe(1);
    expect(state.todayAction.id).toBe("camp21-day-1");
    expect(state.todayAction.recommendationSource).toBe("reviewed_course");
    expect(state.todayAction.status).toBe("not_started");
  });

  it("records an action receipt without turning reflection into fact or external effect", () => {
    const activated = familyMobileReducer(initialFamilyMobileState, { type: "activate_camp_day", day: 1 });
    const started = familyMobileReducer(activated, { type: "start_action" });
    const completed = familyMobileReducer(started, { type: "complete_action", reflection: "我先听完了。" });

    expect(completed.todayAction.status).toBe("checked_in");
    expect(completed.campCompletedDays).toEqual([1]);
    expect(completed.campCurrentDay).toBe(2);
    expect(completed.lastReceipt).toMatchObject({
      actionId: "camp21-day-1",
      reflection: "我先听完了。",
      reflectionKind: "perspective",
      externalEffect: false,
    });
  });

  it("is idempotent for the completed-day ledger", () => {
    const activated = familyMobileReducer(initialFamilyMobileState, { type: "activate_camp_day", day: 1 });
    const first = familyMobileReducer(activated, { type: "complete_action", reflection: "第一次" });
    const replay = familyMobileReducer(first, { type: "complete_action", reflection: "重放" });

    expect(replay.campCompletedDays).toEqual([1]);
  });
});

describe("six-loop controlled mobile actions", () => {
  it("covers growth, plan, assessment, service, commerce, and community across registry and policies", () => {
    const loops = new Set([
      ...FAMILY_SCREENS.map((screen) => screen.loop),
      ...Object.values(UI_ACTION_POLICIES).filter(Boolean).map((policy) => policy!.loop),
    ]);

    expect(loops).toEqual(new Set(["成长", "计划", "评估", "服务", "商业", "社区"]));
  });

  it("records a service intent as an idempotent no-external-effect receipt", () => {
    const policy = UI_ACTION_POLICIES["UI-21"]!;
    const action = {
      type: "record_ui_action" as const,
      payload: {
        screenId: policy.screenId,
        loop: policy.loop,
        kind: policy.kind,
        label: "保存咨询意向",
        message: policy.receiptMessage,
      },
    };
    const first = familyMobileReducer(initialFamilyMobileState, action);
    const replay = familyMobileReducer(first, action);

    expect(replay.uiActionReceipts).toHaveLength(1);
    expect(replay.uiActionReceipts[0]).toMatchObject({ screenId: "UI-21", kind: "service_intent", externalEffect: false });
  });
});

describe("family assessment and 90-day journey", () => {
  it("keeps five bounded family focus areas with three scenario questions each", () => {
    expect(GROWTH_FOCUSES).toHaveLength(5);
    expect(GROWTH_FOCUSES.every((focus) => focus.questions.length === 3)).toBe(true);
  });

  it("stores parent answers as local perspective inputs and tracks completion", () => {
    const selected = familyMobileReducer(initialFamilyMobileState, {
      type: "select_growth_focus",
      focus: "PARENT_CHILD_COMMUNICATION",
    });
    const answered = GROWTH_FOCUSES[0].questions.reduce(
      (state, question) => familyMobileReducer(state, { type: "answer_assessment", questionId: question.id, answer: "sometimes" }),
      selected,
    );

    expect(answered.selectedGrowthFocus).toBe("PARENT_CHILD_COMMUNICATION");
    expect(assessmentCompletion(answered.selectedGrowthFocus, answered.assessmentAnswers)).toBe(1);
    expect(answered.assessmentSyncState).toBe("local");
    expect(Object.values(answered.assessmentAnswers)).toEqual(["sometimes", "sometimes", "sometimes"]);
  });

  it("uses four ordered phases and focus-specific weekly actions", () => {
    expect(MOBILE_JOURNEY_PHASES.map((phase) => phase.id)).toEqual(["SEE", "PARENT_FIRST", "CO_CREATE", "STABILIZE"]);
    expect(getJourneyWeeklyAction("DEVICE_USE_CONTEXT")).toContain("手机规则");
  });
});

describe("Family API mobile contract", () => {
  it("uses account Bearer, omits cookies, and calls family contexts", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ account_id: "account-1", contexts: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })) as unknown as typeof fetch;
    const client = new FamilyApiClient("https://family.example/", fetcher);

    await client.getContexts("fam_token");

    expect(fetcher).toHaveBeenCalledTimes(1);
    const [url, request] = vi.mocked(fetcher).mock.calls[0];
    expect(url).toBe("https://family.example/auth/contexts");
    expect(request?.credentials).toBe("omit");
    expect(request?.headers).toMatchObject({ Authorization: "Bearer fam_token" });
  });

  it("sends an idempotency key for private service drafts without external-effect fields", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ state: "CREATED", external_effect: false }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })) as unknown as typeof fetch;
    const client = new FamilyApiClient("https://family.example", fetcher);

    await client.createPrivateCheckinDraft("fam_token", "family-1", "onboarding-1", "WEEKLY_ACTION_SEE", "idem-1");

    const [url, request] = vi.mocked(fetcher).mock.calls[0];
    expect(url).toContain("/families/family-1/growth/onboardings/onboarding-1/service-journey/checkin-drafts");
    expect(request?.method).toBe("POST");
    expect(request?.headers).toMatchObject({ "idempotency-key": "idem-1", Authorization: "Bearer fam_token" });
    expect(JSON.parse(request?.body as string)).toEqual({ action_ref: "WEEKLY_ACTION_SEE" });
  });

  it("reads post-UI-10 surfaces from the same family-scoped platform projection", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ projection_version: "DEV_PLATFORM_SURFACES_V1", cards: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })) as unknown as typeof fetch;
    const client = new FamilyApiClient("https://family.example", fetcher);

    await client.getDevPlatformSurfaces("fam_token", "family-1");

    const [url, request] = vi.mocked(fetcher).mock.calls[0];
    expect(url).toBe("https://family.example/families/family-1/dev/platform-surfaces");
    expect(request?.credentials).toBe("omit");
    expect(request?.headers).toMatchObject({ Authorization: "Bearer fam_token" });
  });

  it("records only an idempotent UI-26 no-op receipt without publishing content or contact fields", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ external_effect: false, status: "RECORDED" }), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    })) as unknown as typeof fetch;
    const client = new FamilyApiClient("https://family.example", fetcher);

    await client.recordDevFlowEvent("fam_token", "family-1", {
      ui_id: "UI-26",
      command: "ACK_SYNTHETIC_POST_DRAFT",
      selection: "GROWTH_CHECKIN:亲子沟通",
    }, "community-idempotency-1");

    const [url, request] = vi.mocked(fetcher).mock.calls[0];
    const body = JSON.parse(request?.body as string);
    expect(url).toBe("https://family.example/families/family-1/dev/flow-events");
    expect(request?.headers).toMatchObject({ "idempotency-key": "community-idempotency-1", Authorization: "Bearer fam_token" });
    expect(body).toEqual({ ui_id: "UI-26", command: "ACK_SYNTHETIC_POST_DRAFT", selection: "GROWTH_CHECKIN:亲子沟通" });
    expect(JSON.stringify(body)).not.toMatch(/title|body|media|publish|comment|recipient|notification|phone|address|child_name/i);
  });

  it("reads commerce and membership projections from the existing family-scoped API", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ products: [], plans: [], subscriptions: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })) as unknown as typeof fetch;
    const client = new FamilyApiClient("https://family.example", fetcher);

    await client.getCommerceProducts("fam_token", "family-1");
    await client.getCommerceCustomerProjection("fam_token", "family-1");
    await client.getMembershipPlans("fam_token", "family-1");
    await client.getMembershipCustomerProjection("fam_token", "family-1");

    expect(vi.mocked(fetcher).mock.calls.map(([url]) => url)).toEqual([
      "https://family.example/families/family-1/orchestration/test-loop/commerce/products",
      "https://family.example/families/family-1/orchestration/test-loop/commerce/customer-projection",
      "https://family.example/families/family-1/orchestration/test-loop/membership/plans",
      "https://family.example/families/family-1/orchestration/test-loop/membership/customer-projection",
    ]);
    for (const [, request] of vi.mocked(fetcher).mock.calls) {
      expect(request?.credentials).toBe("omit");
      expect(request?.headers).toMatchObject({ Authorization: "Bearer fam_token" });
    }
  });

  it("submits only a versioned UI-14 intent with idempotency and no payment fields", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ intent: { external_effect: false }, entitlement: { external_effect: false } }), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    })) as unknown as typeof fetch;
    const client = new FamilyApiClient("https://family.example", fetcher);

    await client.submitCommerceIntent("fam_token", "family-1", {
      page_id: "UI-14",
      product_ref: "PRODUCT_PARENT_CHILD_CAMP",
      product_version: 1,
      attributes: { entry: "family_ai_mobile_product_detail" },
    }, "intent-idempotency-1");

    const [url, request] = vi.mocked(fetcher).mock.calls[0];
    const body = JSON.parse(request?.body as string);
    expect(url).toContain("/families/family-1/orchestration/test-loop/commerce/order-intents");
    expect(request?.method).toBe("POST");
    expect(request?.headers).toMatchObject({ "idempotency-key": "intent-idempotency-1", Authorization: "Bearer fam_token" });
    expect(body).toMatchObject({ page_id: "UI-14", product_ref: "PRODUCT_PARENT_CHILD_CAMP", product_version: 1 });
    expect(JSON.stringify(body)).not.toMatch(/payment|price|currency|contact|recipient|external_effect/i);
  });

  it("reads service supply, slots, and family-private customer projection from the existing Family API", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ offerings: [], slots: [], bookings: [], service_records: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    })) as unknown as typeof fetch;
    const client = new FamilyApiClient("https://family.example", fetcher);

    await client.getServiceOfferings("fam_token", "family-1", { availableOnly: true });
    await client.getServiceSlots("fam_token", "family-1", "TEST_PARENT_CHILD_DIALOGUE", 1);
    await client.getServiceCustomerProjection("fam_token", "family-1");

    expect(vi.mocked(fetcher).mock.calls.map(([url]) => url)).toEqual([
      "https://family.example/families/family-1/orchestration/test-loop/services/offerings?page_id=UI-19&available_only=true",
      "https://family.example/families/family-1/orchestration/test-loop/services/slots?service_offering_ref=TEST_PARENT_CHILD_DIALOGUE&service_offering_version=1",
      "https://family.example/families/family-1/orchestration/test-loop/services/customer-projection",
    ]);
    for (const [, request] of vi.mocked(fetcher).mock.calls) {
      expect(request?.credentials).toBe("omit");
      expect(request?.headers).toMatchObject({ Authorization: "Bearer fam_token" });
    }
  });

  it("submits only an idempotent UI-21 service request with no payment, notification, provider, or raw child fields", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ booking: { external_effect: false }, service_record: { external_effect: false } }), {
      status: 201,
      headers: { "Content-Type": "application/json" },
    })) as unknown as typeof fetch;
    const client = new FamilyApiClient("https://family.example", fetcher);

    await client.submitServiceBooking("fam_token", "family-1", {
      page_id: "UI-21",
      service_offering_ref: "TEST_PARENT_CHILD_DIALOGUE",
      service_offering_version: 1,
      availability_slot_ref: "TEST_SLOT_001",
      attributes: { entry: "family_ai_mobile_consultation_need", channel_preference: "VIDEO" },
    }, "service-idempotency-1");

    const [url, request] = vi.mocked(fetcher).mock.calls[0];
    const body = JSON.parse(request?.body as string);
    expect(url).toBe("https://family.example/families/family-1/orchestration/test-loop/services/booking-requests");
    expect(request?.method).toBe("POST");
    expect(request?.headers).toMatchObject({ "idempotency-key": "service-idempotency-1", Authorization: "Bearer fam_token" });
    expect(body).toMatchObject({ page_id: "UI-21", service_offering_ref: "TEST_PARENT_CHILD_DIALOGUE", service_offering_version: 1, availability_slot_ref: "TEST_SLOT_001" });
    expect(JSON.stringify(body)).not.toMatch(/payment|price|currency|recipient|notification|provider_ref|child_name|phone|address|diagnosis/i);
  });

  it("surfaces required-mode 401 errors instead of silently falling back to another family", async () => {
    const fetcher = vi.fn(async () => new Response(JSON.stringify({ message: "bearer_token_required" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    })) as unknown as typeof fetch;
    const client = new FamilyApiClient("https://family.example", fetcher);

    await expect(client.getContexts("expired")).rejects.toMatchObject({
      status: 401,
      code: "bearer_token_required",
    });
  });

  it("keeps local synthetic mode explicit when the Family API URL is absent", async () => {
    const client = new FamilyApiClient("");

    expect(client.configured).toBe(false);
    await expect(client.getContexts("token")).rejects.toMatchObject({
      code: "FAMILY_API_NOT_CONFIGURED",
    });
  });
});

describe("child autonomy and private family storytelling", () => {
  it("selects UI-10 through UI-12 from the existing Family API projections without redefining their boundaries", () => {
    const childPrompt = {
      state: "ACTION_RECORDED",
      focus: "PARENT_CHILD_COMMUNICATION",
      headline: "今天可以一起试一件小事",
      shared_action: "先听完彼此的一句话。",
      pause_hint: "今天暂停也可以。",
      action_route: "growth-daily-task",
      fact_boundary: "ACTION_RECORDED_NOT_CHILD_OUTCOME",
    } as const;
    const journey = {
      state: "IN_PROGRESS",
      headline: "我们已经走过的几步",
      entries: [{ event_id: "event-1", label: "记录行动", detail: "保留过程。" }],
      fact_boundary: "PROCESS_EVENTS_NOT_OUTCOME_OR_RANKING",
    } as const;
    const story = {
      state: "READY",
      title: "我们一起走过的片段",
      summary: "只回看过程。",
      moments: ["完成一次家庭行动。"],
      fact_boundary: "PROCESS_EVENTS_NOT_OUTCOME_OR_SHARE",
    } as const;
    const core = {
      projection_version: "DEV_CORE_GROWTH_V1",
      family_id: "family-1",
      data_source: "SYNTHETIC_DEV_ONLY",
      model_gateway: { status: "NOOP_NOT_INVOKED", rule: "NO_FREE_TEXT_MODEL_WRITE_TO_CORE_ONTOLOGY" },
      cards: [{ surface: "UI-10", child_action_prompt: childPrompt }],
    } satisfies FamilyApiCoreGrowthProjection;
    const platform = {
      projection_version: "DEV_PLATFORM_SURFACES_V1",
      family_id: "family-1",
      data_source: "SYNTHETIC_DEV_ONLY",
      external_effect_adapter: "NOOP_NOT_INVOKED",
      model_gateway: "NOOP_NOT_INVOKED",
      cards: [
        { surface: "UI-11", personal_growth_journey: journey },
        { surface: "UI-12", private_growth_story: story },
      ],
    } satisfies FamilyApiPlatformSurfacesProjection;

    expect(selectChildActionPrompt(core)?.fact_boundary).toBe("ACTION_RECORDED_NOT_CHILD_OUTCOME");
    expect(selectPersonalGrowthJourney(platform)?.fact_boundary).toBe("PROCESS_EVENTS_NOT_OUTCOME_OR_RANKING");
    expect(selectPrivateGrowthStory(platform)?.fact_boundary).toBe("PROCESS_EVENTS_NOT_OUTCOME_OR_SHARE");
  });

  it("offers try, change, and pause on every child prompt without score or reward fields", () => {
    expect(CHILD_PRACTICE_PROMPTS.length).toBeGreaterThanOrEqual(3);
    for (const prompt of CHILD_PRACTICE_PROMPTS) {
      expect(prompt.choices.map((choice) => choice.id)).toEqual(["TRY_THIS", "CHOOSE_ANOTHER", "PAUSE_TODAY"]);
      expect(JSON.stringify(prompt)).not.toMatch(/score|rank|reward|badge|streak/i);
    }
  });

  it("records pause as a private child perspective rather than fact, failure, or external effect", () => {
    const paused = familyMobileReducer(initialFamilyMobileState, {
      type: "record_child_choice",
      promptId: "choose-family-moment",
      choice: "PAUSE_TODAY",
    });

    expect(paused.childChoiceDraft).toMatchObject({
      choice: "PAUSE_TODAY",
      perspectiveKind: "child_choice_perspective_not_fact",
      visibility: "FAMILY_PRIVATE",
      externalEffect: false,
    });
    expect(JSON.stringify(paused.childChoiceDraft)).not.toMatch(/failure|ability|diagnosis|score|rank/i);
  });

  it("builds only same-family process events without ranking, points, percentile, or child outcomes", () => {
    const selected = familyMobileReducer(initialFamilyMobileState, {
      type: "select_growth_focus",
      focus: "PARENT_CHILD_COMMUNICATION",
    });
    const withChoice = familyMobileReducer(selected, {
      type: "record_child_choice",
      promptId: "finish-my-sentence",
      choice: "TRY_THIS",
    });
    const events = buildFamilyRhythmEvents({
      selectedGrowthFocus: withChoice.selectedGrowthFocus,
      lastReceipt: withChoice.lastReceipt,
      campCompletedDays: withChoice.campCompletedDays,
      uiActionReceipts: withChoice.uiActionReceipts,
      childChoiceDraft: withChoice.childChoiceDraft,
    });

    expect(events).toHaveLength(2);
    expect(events.every((event) => event.evidenceBoundary === "process_event_not_outcome")).toBe(true);
    expect(events.flatMap((event) => Object.keys(event))).not.toEqual(expect.arrayContaining(["rank", "score", "percentile", "points", "badge", "reward", "outcome"]));
    expect(events.map((event) => `${event.title} ${event.detail}`).join(" ")).not.toMatch(/排名|总分|百分位|积分|勋章|奖励|成长结果/);
  });

  it("creates a maximum four-event private story draft with no media, share, publish, or notification effect", () => {
    const events = Array.from({ length: 6 }, (_, index) => ({
      id: `event-${index}`,
      title: `家庭过程 ${index}`,
      detail: "记录一次家庭尝试。",
      sourceUi: "UI-09" as const,
      occurredAt: "",
      kind: "family_action" as const,
      evidenceBoundary: "process_event_not_outcome" as const,
    }));
    const story = buildPrivateGrowthStory(events, "我们想继续慢一点说话。");

    expect(story).toMatchObject({
      visibility: "FAMILY_PRIVATE",
      state: "PRIVATE_DRAFT",
      perspectiveKind: "family_narrative_not_fact_or_outcome",
      externalEffect: false,
    });
    expect(story.sourceEventIds).toHaveLength(4);
    expect(JSON.stringify(story)).not.toMatch(/share|publish|recipient|notification|download|qrcode|photo|school|child_name/i);
  });
});

describe("commerce and membership mobile presentation", () => {
  it("merges admitted Family API products into the existing Web baseline without dropping baseline screens", () => {
    const remote = [{
      product_id: "product-1",
      product_ref: "PRODUCT_PARENT_CHILD_CAMP",
      product_version: 1,
      title: "21天亲子沟通挑战营（测试）",
      admission_status: "ADMITTED",
      source_ref: "TEST_FIXTURE",
      fixture_only: true,
      attributes_schema_version: 1,
    }] satisfies FamilyApiCommerceProduct[];
    const display = commerceProductsForDisplay(remote);

    expect(display).toHaveLength(EXISTING_COMMERCE_PRESENTATION.length);
    expect(display[0]).toMatchObject({ productRef: "PRODUCT_PARENT_CHILD_CAMP", title: "21天亲子沟通挑战营（测试）", source: "FAMILY_API", fixtureOnly: true });
    expect(display.map((item) => item.title)).toEqual(expect.arrayContaining(["家庭成长测评卡", "亲子阅读工具包", "家庭专注力提升训练营"]));
  });

  it("keeps commerce, invitation, and study-group drafts family private with no external effect", () => {
    const commerce = familyMobileReducer(initialFamilyMobileState, {
      type: "save_commerce_intent_draft",
      productRef: "PRODUCT_PARENT_CHILD_CAMP",
      productVersion: 1,
      productTitle: "21天亲子沟通挑战营",
    });
    const invitation = familyMobileReducer(commerce, {
      type: "save_invitation_draft",
      productRef: "PRODUCT_PARENT_CHILD_CAMP",
      productTitle: "21天亲子沟通挑战营",
    });
    const group = familyMobileReducer(invitation, {
      type: "save_study_group_draft",
      productRef: "PRODUCT_PARENT_CHILD_CAMP",
      productTitle: "21天亲子沟通挑战营",
      familyCount: 3,
    });

    expect(group.commerceIntentDraft).toMatchObject({ state: "LOCAL_DRAFT", visibility: "FAMILY_PRIVATE", externalEffect: false });
    expect(group.invitationDraft).toMatchObject({ state: "PRIVATE_DRAFT", visibility: "FAMILY_PRIVATE", externalEffect: false });
    expect(group.studyGroupDraft).toMatchObject({ familyCount: 3, state: "PRIVATE_DRAFT", visibility: "FAMILY_PRIVATE", externalEffect: false });
    expect(JSON.stringify({ commerce: group.commerceIntentDraft, invitation: group.invitationDraft, group: group.studyGroupDraft })).not.toMatch(/payment|charged|contact|recipient|notification|share_url|qrcode/i);
  });

  it("syncs only the existing intent and entitlement receipt identities", () => {
    const local = familyMobileReducer(initialFamilyMobileState, {
      type: "save_commerce_intent_draft",
      productRef: "PRODUCT_PARENT_CHILD_CAMP",
      productVersion: 1,
      productTitle: "21天亲子沟通挑战营",
    });
    const synced = familyMobileReducer(local, {
      type: "sync_commerce_intent_receipt",
      intentId: "intent-1",
      entitlementId: "entitlement-1",
    });

    expect(synced.commerceIntentDraft).toMatchObject({ state: "SYNCED_RECEIPT", intentId: "intent-1", entitlementId: "entitlement-1", externalEffect: false });
  });
});

describe("expert service and family activity mobile presentation", () => {
  it("maps admitted teacher supply into the existing teacher-zone baseline without inventing provider facts", () => {
    const remote = [{
      service_offering_id: "offering-1",
      service_offering_ref: "TEST_PARENT_CHILD_DIALOGUE",
      version_no: 1,
      title: "亲子沟通支持",
      provider_ref: "TEACHER_LI",
      provider_display_name: "李老师",
      provider_kind: "TEACHER",
      qualification_status: "ACTIVE",
      admission_status: "ADMITTED",
      offering_status: "ACTIVE",
      service_type: "亲子沟通",
      age_band: "学龄儿童家庭",
      next_available_at: "2026-08-24T10:00:00.000Z",
      next_available_channel: "VIDEO",
      availability_status: "AVAILABLE",
      fixture_only: true,
      attributes_schema_version: 1,
    }] satisfies FamilyApiServiceOffering[];

    const display = serviceOfferingsForDisplay(remote);
    expect(display).toHaveLength(1);
    expect(display[0]).toMatchObject({ offeringRef: "TEST_PARENT_CHILD_DIALOGUE", providerName: "李老师", theme: "COMMUNICATION", source: "FAMILY_API", fixtureOnly: true });
    expect(JSON.stringify(display[0])).not.toMatch(/score|rating|rank|recommended_for_family|diagnosis/i);
  });

  it("selects the UI-22 activity catalog from the same platform projection and keeps browsing separate from registration", () => {
    const catalog = {
      state: "READY",
      headline: "家庭成长活动",
      introduction: "先了解主题。",
      activities: [{ activity_ref: "ACTIVITY_PARENT_CHILD_DIALOGUE", title: "亲子沟通小练习", summary: "交换彼此的想法。", age_hint: "学龄儿童家庭", detail_route: "activity-detail" }],
      support_topics_route: "teacher-zone",
      fact_boundary: "ACTIVITY_BROWSING_NOT_REGISTRATION_ATTENDANCE_OR_OUTCOME",
    } as const;
    const platform = {
      projection_version: "DEV_PLATFORM_SURFACES_V1",
      family_id: "family-1",
      data_source: "SYNTHETIC_DEV_ONLY",
      external_effect_adapter: "NOOP_NOT_INVOKED",
      model_gateway: "NOOP_NOT_INVOKED",
      cards: [{ surface: "UI-22", family_growth_activity_catalog: catalog }],
    } satisfies FamilyApiPlatformSurfacesProjection;

    const selected = selectGrowthActivityCatalog(platform);
    const display = growthActivitiesForDisplay(selected?.activities);
    expect(selected?.fact_boundary).toBe("ACTIVITY_BROWSING_NOT_REGISTRATION_ATTENDANCE_OR_OUTCOME");
    expect(display[0]).toMatchObject({ activityRef: "ACTIVITY_PARENT_CHILD_DIALOGUE", source: "FAMILY_API" });
  });

  it("keeps consultation needs and activity interests family private without external messaging or outcome claims", () => {
    const consultation = familyMobileReducer(initialFamilyMobileState, {
      type: "save_consultation_need_draft",
      offeringRef: "TEST_PARENT_CHILD_DIALOGUE",
      offeringVersion: 1,
      offeringTitle: "亲子沟通支持",
      providerName: "李老师",
      channel: "VIDEO",
      slotRef: "TEST_SLOT_001",
      timePreference: "周三 10:00",
      ageBand: "7–9 岁",
      needFocus: "家长想先了解沟通节奏",
    });
    const activity = familyMobileReducer(consultation, { type: "save_activity_interest_draft", activityRef: "ACTIVITY_PARENT_CHILD_DIALOGUE", activityTitle: "亲子沟通小练习" });

    expect(activity.consultationNeedDraft).toMatchObject({ state: "LOCAL_DRAFT", visibility: "FAMILY_PRIVATE", consentAcknowledged: true, externalEffect: false });
    expect(activity.activityInterestDraft).toMatchObject({ state: "PRIVATE_DRAFT", visibility: "FAMILY_PRIVATE", externalEffect: false });
    expect(JSON.stringify({ consultation: activity.consultationNeedDraft, activity: activity.activityInterestDraft })).not.toMatch(/recipient|notification|calendar_event|payment|confirmed_service|diagnosis|outcome|score|rank/i);
  });

  it("syncs only booking and service-record receipt identities after the server accepts a request", () => {
    const local = familyMobileReducer(initialFamilyMobileState, {
      type: "save_consultation_need_draft",
      offeringRef: "TEST_PARENT_CHILD_DIALOGUE",
      offeringVersion: 1,
      offeringTitle: "亲子沟通支持",
      providerName: "李老师",
      channel: "VIDEO",
      slotRef: "TEST_SLOT_001",
      timePreference: "周三 10:00",
      ageBand: "7–9 岁",
      needFocus: "家长想先了解沟通节奏",
    });
    const synced = familyMobileReducer(local, { type: "sync_consultation_need_receipt", bookingRequestId: "booking-1", serviceRecordId: "record-1" });
    expect(synced.consultationNeedDraft).toMatchObject({ state: "SYNCED_RECEIPT", bookingRequestId: "booking-1", serviceRecordId: "record-1", externalEffect: false });
  });
});

describe("community content and private family notes", () => {
  it("selects the UI-25 moderated experience feed from the same platform projection", () => {
    const feed = {
      state: "READY",
      headline: "看看其他家庭的日常小经验",
      introduction: "先读一读，再决定哪些想法适合自己的家庭。",
      entries: [{ exchange_ref: "EXCHANGE_DIALOGUE_PAUSE", title: "给一次对话留一点停顿", summary: "先停一停。", topic: "亲子沟通", detail_route: "dynamic-detail" }],
      activity_catalog_route: "salon-list",
      fact_boundary: "READING_EXPERIENCE_SUMMARIES_NOT_PUBLICATION_INTERACTION_OR_OUTCOME",
    } as const;
    const platform = {
      projection_version: "DEV_PLATFORM_SURFACES_V1",
      family_id: "family-1",
      data_source: "SYNTHETIC_DEV_ONLY",
      external_effect_adapter: "NOOP_NOT_INVOKED",
      model_gateway: "NOOP_NOT_INVOKED",
      cards: [{ surface: "UI-25", family_learning_exchange_feed: feed }],
    } satisfies FamilyApiPlatformSurfacesProjection;

    expect(selectLearningExchangeFeed(platform)?.fact_boundary).toBe("READING_EXPERIENCE_SUMMARIES_NOT_PUBLICATION_INTERACTION_OR_OUTCOME");
    expect(selectLearningExchangeEntry(platform, "EXCHANGE_DIALOGUE_PAUSE")?.title).toBe("给一次对话留一点停顿");
    expect(communityEntriesForDisplay(feed.entries)[0]).toMatchObject({ exchangeRef: "EXCHANGE_DIALOGUE_PAUSE", source: "FAMILY_API" });
  });

  it("stores a family note as parent perspective and never as a public post or fact", () => {
    const state = familyMobileReducer(initialFamilyMobileState, {
      type: "save_community_post_draft",
      kind: "GROWTH_CHECKIN",
      title: "今天我们慢一点说话",
      body: "我试着先听完，再回应。",
      topic: "亲子沟通",
    });

    expect(state.communityPostDraft).toMatchObject({ state: "PRIVATE_DRAFT", visibility: "FAMILY_PRIVATE", perspectiveKind: "PARENT_PERSPECTIVE_NOT_FACT", privacyReview: "ACKNOWLEDGED", externalEffect: false });
    expect(JSON.stringify(state.communityPostDraft)).not.toMatch(/published|public_url|media|recipient|notification|like_count|comment_count/i);
  });

  it("keeps bookmark, follow, and response as one family-private interaction draft", () => {
    const bookmarked = familyMobileReducer(initialFamilyMobileState, { type: "toggle_community_bookmark", exchangeRef: "EXCHANGE_DIALOGUE_PAUSE" });
    const followed = familyMobileReducer(bookmarked, { type: "toggle_community_follow", exchangeRef: "EXCHANGE_DIALOGUE_PAUSE" });
    const responded = familyMobileReducer(followed, { type: "save_community_response_draft", exchangeRef: "EXCHANGE_DIALOGUE_PAUSE", responseText: "我想先试试停顿。" });
    const draft = responded.communityInteractionDrafts.EXCHANGE_DIALOGUE_PAUSE;

    expect(draft).toMatchObject({ bookmarked: true, following: true, responseText: "我想先试试停顿。", visibility: "FAMILY_PRIVATE", perspectiveKind: "PARENT_PERSPECTIVE_NOT_PUBLIC_COMMENT", externalEffect: false });
    expect(JSON.stringify(draft)).not.toMatch(/notification|recipient|like_count|comment_count|follower_count/i);
  });

  it("flags direct family identifiers before a private note can be saved", () => {
    expect(detectCommunityPrivacyRisks("孩子在阳光小学三年级，电话 13812345678")).toEqual(expect.arrayContaining(["请移除手机号码", "请避免填写学校、班级或住址"]));
    expect(detectCommunityPrivacyRisks("今天我们一起读了十分钟书。")) .toEqual([]);
  });
});
