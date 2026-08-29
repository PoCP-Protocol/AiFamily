import type {
  FamilyApiGrowthActivity,
  FamilyApiServiceOffering,
} from "./family-api-projections";

export type SupportThemeId = "ALL" | "COMMUNICATION" | "STUDY" | "EMOTION" | "FAMILY" | "FOCUS";
export type ConsultationChannel = "VIDEO" | "TEXT" | "OFFLINE";

export interface SupportOfferingPresentation {
  offeringRef: string;
  version: number;
  title: string;
  providerRef: string;
  providerName: string;
  serviceType: string;
  ageBand: string;
  theme: Exclude<SupportThemeId, "ALL">;
  nextAvailableAt: string | null;
  channel: ConsultationChannel | null;
  availability: "AVAILABLE" | "UNAVAILABLE";
  source: "FAMILY_API" | "BASELINE_CONTENT";
  fixtureOnly: true;
  accent: string;
  introduction: string;
  expertise: readonly string[];
}

export interface GrowthActivityPresentation {
  activityRef: string;
  title: string;
  summary: string;
  ageHint: string;
  theme: "亲子沟通" | "学习习惯" | "情绪陪伴" | "家庭关系";
  scheduleLabel: string;
  locationLabel: string;
  source: "FAMILY_API" | "BASELINE_CONTENT";
  accent: string;
  highlights: readonly string[];
  agenda: readonly string[];
}

export interface ConsultationNeedDraft {
  id: string;
  offeringRef: string;
  offeringVersion: number;
  offeringTitle: string;
  providerName: string;
  channel: ConsultationChannel;
  slotRef: string | null;
  timePreference: string;
  ageBand: string;
  needFocus: string;
  consentAcknowledged: true;
  state: "LOCAL_DRAFT" | "SYNCED_RECEIPT";
  bookingRequestId: string | null;
  serviceRecordId: string | null;
  visibility: "FAMILY_PRIVATE";
  externalEffect: false;
  recordedAt: string;
}

export interface ActivityInterestDraft {
  id: string;
  activityRef: string;
  activityTitle: string;
  state: "PRIVATE_DRAFT";
  visibility: "FAMILY_PRIVATE";
  externalEffect: false;
  recordedAt: string;
}

export const SUPPORT_THEMES: readonly { id: SupportThemeId; label: string; color: string }[] = [
  { id: "ALL", label: "全部", color: "#2563EB" },
  { id: "COMMUNICATION", label: "亲子沟通", color: "#2563EB" },
  { id: "STUDY", label: "学习习惯", color: "#7556C8" },
  { id: "EMOTION", label: "情绪管理", color: "#F26C5B" },
  { id: "FAMILY", label: "家庭关系", color: "#D84D83" },
  { id: "FOCUS", label: "专注力", color: "#16866D" },
] as const;

const FALLBACK_OFFERINGS: readonly SupportOfferingPresentation[] = [
  {
    offeringRef: "TEST_PARENT_CHILD_DIALOGUE",
    version: 1,
    title: "亲子沟通支持",
    providerRef: "TEACHER_LI",
    providerName: "李老师",
    serviceType: "亲子沟通",
    ageBand: "学龄儿童家庭",
    theme: "COMMUNICATION",
    nextAvailableAt: null,
    channel: "VIDEO",
    availability: "AVAILABLE",
    source: "BASELINE_CONTENT",
    fixtureOnly: true,
    accent: "#2563EB",
    introduction: "从一次具体对话开始，帮助家长梳理倾听、回应与家庭沟通节奏。",
    expertise: ["亲子沟通", "情绪管理", "家庭关系"],
  },
  {
    offeringRef: "TEST_STUDY_HABIT_GUIDANCE",
    version: 1,
    title: "学习习惯支持",
    providerRef: "TEACHER_WANG",
    providerName: "王老师",
    serviceType: "学习习惯",
    ageBand: "学龄儿童家庭",
    theme: "STUDY",
    nextAvailableAt: null,
    channel: "TEXT",
    availability: "AVAILABLE",
    source: "BASELINE_CONTENT",
    fixtureOnly: true,
    accent: "#7556C8",
    introduction: "围绕日常作业、节奏与家庭协作，先了解当前场景，再讨论可尝试的小步骤。",
    expertise: ["学习习惯", "专注力", "家庭协作"],
  },
] as const;

export function serviceOfferingsForDisplay(remote?: readonly FamilyApiServiceOffering[]) {
  if (!remote?.length) return [...FALLBACK_OFFERINGS];
  return remote.map((item, index): SupportOfferingPresentation => ({
    offeringRef: item.service_offering_ref,
    version: item.version_no,
    title: item.title,
    providerRef: item.provider_ref,
    providerName: item.provider_display_name,
    serviceType: item.service_type || "家庭成长支持",
    ageBand: item.age_band || "家庭阶段待了解",
    theme: inferSupportTheme(item.service_type),
    nextAvailableAt: item.next_available_at,
    channel: item.next_available_channel,
    availability: item.availability_status,
    source: "FAMILY_API",
    fixtureOnly: item.fixture_only,
    accent: index % 2 === 0 ? "#2563EB" : "#7556C8",
    introduction: "从家庭当前情境出发，先了解支持方向、适用场景和服务边界，再决定是否需要继续。",
    expertise: [item.service_type || "家庭成长", item.age_band || "家庭支持", channelLabel(item.next_available_channel)],
  }));
}

const FALLBACK_ACTIVITIES: readonly GrowthActivityPresentation[] = [
  {
    activityRef: "ACTIVITY_PARENT_CHILD_DIALOGUE",
    title: "高质量亲子沟通沙龙",
    summary: "围绕一次日常对话，交换彼此的想法。",
    ageHint: "适龄参考：学龄儿童家庭",
    theme: "亲子沟通",
    scheduleLabel: "近期周末 · 14:00–16:30",
    locationLabel: "活动方式与地点待确认",
    source: "BASELINE_CONTENT",
    accent: "#16866D",
    highlights: ["家庭沟通方法与工具", "真实情境小组练习", "留下一个可尝试的小行动"],
    agenda: ["暖场与家庭情境", "主题分享", "互动练习", "家庭行动卡", "交流与答疑"],
  },
  {
    activityRef: "ACTIVITY_FAMILY_READING",
    title: "家庭阅读时光工作坊",
    summary: "用一本喜欢的书，留出一段轻松的共读时间。",
    ageHint: "适龄参考：亲子共读家庭",
    theme: "学习习惯",
    scheduleLabel: "近期周末 · 14:00–16:30",
    locationLabel: "活动方式与地点待确认",
    source: "BASELINE_CONTENT",
    accent: "#F28C45",
    highlights: ["把共读放进日常", "亲子共同选择内容", "不以阅读数量评价孩子"],
    agenda: ["家庭阅读现状", "共读方法", "亲子选择练习", "家庭阅读计划", "交流与答疑"],
  },
] as const;

export function growthActivitiesForDisplay(remote?: readonly FamilyApiGrowthActivity[]) {
  if (!remote?.length) return [...FALLBACK_ACTIVITIES];
  return remote.map((item, index): GrowthActivityPresentation => {
    const fallback = FALLBACK_ACTIVITIES.find((candidate) => candidate.activityRef === item.activity_ref);
    return {
      activityRef: item.activity_ref,
      title: item.title,
      summary: item.summary,
      ageHint: item.age_hint,
      theme: fallback?.theme ?? (index % 2 === 0 ? "亲子沟通" : "家庭关系"),
      scheduleLabel: fallback?.scheduleLabel ?? "活动时间待确认",
      locationLabel: fallback?.locationLabel ?? "活动方式与地点待确认",
      source: "FAMILY_API",
      accent: fallback?.accent ?? "#2563EB",
      highlights: fallback?.highlights ?? ["了解活动主题", "确认适用家庭", "由家庭决定是否继续"],
      agenda: fallback?.agenda ?? ["主题说明", "方法分享", "家庭练习", "交流与答疑"],
    };
  });
}

export function channelLabel(channel: ConsultationChannel | null) {
  if (channel === "VIDEO") return "视频交流";
  if (channel === "TEXT") return "文字交流";
  if (channel === "OFFLINE") return "线下交流";
  return "安排待确认";
}

function inferSupportTheme(serviceType: string | null): Exclude<SupportThemeId, "ALL"> {
  const value = serviceType ?? "";
  if (/学习|习惯/.test(value)) return "STUDY";
  if (/情绪/.test(value)) return "EMOTION";
  if (/家庭|关系/.test(value)) return "FAMILY";
  if (/专注/.test(value)) return "FOCUS";
  return "COMMUNICATION";
}
