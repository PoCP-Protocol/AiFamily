export type CommunityPostKind = "GROWTH_CHECKIN" | "MILESTONE" | "HELP_REFLECTION" | "EXPERIENCE";

export interface CommunityPostDraft {
  id: string;
  kind: CommunityPostKind;
  title: string;
  body: string;
  topic: string;
  state: "PRIVATE_DRAFT";
  visibility: "FAMILY_PRIVATE";
  perspectiveKind: "PARENT_PERSPECTIVE_NOT_FACT";
  privacyReview: "ACKNOWLEDGED";
  aiTagDraft?: CommunityAiTagDraft;
  recordedAt: string;
  externalEffect: false;
}

export interface CommunityAiTagDraft {
  tags: string[];
  source: "MODEL_GATEWAY" | "RULE_BASED_FALLBACK" | "MANUAL";
  modelGatewayStatus: "INVOKED" | "FALLBACK_RULE_BASED";
  factBoundary: "TAGS_ARE_EDITABLE_PERSPECTIVE_NOT_FACT";
}

export interface CommunityInteractionDraft {
  exchangeRef: string;
  bookmarked: boolean;
  following: boolean;
  responseText: string;
  state: "PRIVATE_DRAFT";
  visibility: "FAMILY_PRIVATE";
  perspectiveKind: "PARENT_PERSPECTIVE_NOT_PUBLIC_COMMENT";
  updatedAt: string;
  externalEffect: false;
}

export interface CommunityEntryPresentation {
  exchangeRef: string;
  title: string;
  summary: string;
  topic: string;
  authorLabel: string;
  timeLabel: string;
  source: "FAMILY_API" | "LOCAL_REFERENCE";
}

export const COMMUNITY_POST_KIND_OPTIONS: readonly { id: CommunityPostKind; label: string; accent: string }[] = [
  { id: "GROWTH_CHECKIN", label: "成长打卡", accent: "#2563EB" },
  { id: "MILESTONE", label: "成长时刻", accent: "#16866D" },
  { id: "HELP_REFLECTION", label: "求助与反思", accent: "#7C5CE5" },
  { id: "EXPERIENCE", label: "经验小记", accent: "#F28C45" },
];

export const COMMUNITY_TOPICS = ["亲子沟通", "家庭阅读", "学习习惯", "情绪陪伴", "同城活动"] as const;
export const PRIVATE_NOTE_TAG_OPTIONS = ["亲子沟通", "家庭阅读", "学习习惯", "情绪陪伴", "共同成长", "日常行动", "家庭反思", "阶段回看", "服务体验", "成长营"] as const;

export function detectCommunityPrivacyRisks(value: string): string[] {
  const risks: string[] = [];
  if (/1[3-9]\d{9}/.test(value)) risks.push("请移除手机号码");
  if (/(微信|wx|wechat|QQ|qq)[：:\s]*[A-Za-z0-9_-]{4,}/.test(value)) risks.push("请移除社交账号");
  if (/(学校|幼儿园|小学|中学|班级|住址|小区|门牌)/.test(value)) risks.push("请避免填写学校、班级或住址");
  if (/(身份证|证件号)/.test(value)) risks.push("请移除证件信息");
  return risks;
}

export function postKindLabel(kind: CommunityPostKind) {
  return COMMUNITY_POST_KIND_OPTIONS.find((item) => item.id === kind)?.label ?? "家庭小记";
}

export function communityEntriesForDisplay(entries?: readonly { exchange_ref: string; title: string; summary: string; topic: string }[]): CommunityEntryPresentation[] {
  const source = entries?.length ? "FAMILY_API" as const : "LOCAL_REFERENCE" as const;
  const values = entries?.length ? entries : [
    { exchange_ref: "EXCHANGE_DIALOGUE_PAUSE", title: "给一次对话留一点停顿", summary: "有家长会在情绪上来时先停一停，等彼此都愿意再继续说。", topic: "亲子沟通" },
    { exchange_ref: "EXCHANGE_READING_ROUTINE", title: "把共读放进睡前的十分钟", summary: "有家庭从一小段喜欢的故事开始，不追求读完多少，只留一点相处时间。", topic: "家庭阅读" },
  ];
  return values.map((entry, index) => ({
    exchangeRef: entry.exchange_ref,
    title: entry.title,
    summary: entry.summary,
    topic: entry.topic,
    authorLabel: index % 2 === 0 ? "一位成长中的家长" : "一个正在练习的家庭",
    timeLabel: "家庭经验摘要",
    source,
  }));
}
