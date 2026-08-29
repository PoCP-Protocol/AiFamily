import { invokeLLM, listLLMModels } from "./_core/llm";

export const PRIVATE_NOTE_TAGS = [
  "亲子沟通",
  "家庭阅读",
  "学习习惯",
  "情绪陪伴",
  "共同成长",
  "日常行动",
  "家庭反思",
  "阶段回看",
  "服务体验",
  "成长营",
] as const;

export type PrivateNoteTag = (typeof PRIVATE_NOTE_TAGS)[number];

export interface PrivateNoteTagInput {
  title: string;
  body: string;
  topic: string;
  privacyAcknowledged: true;
}

export interface PrivateNoteTagSuggestion {
  tags: PrivateNoteTag[];
  source: "MODEL_GATEWAY" | "RULE_BASED_FALLBACK";
  modelGatewayStatus: "INVOKED" | "FALLBACK_RULE_BASED";
  persistence: "NONE";
  externalEffect: false;
  factBoundary: "TAGS_ARE_EDITABLE_PERSPECTIVE_NOT_FACT";
}

type ModelGateway = {
  listModels: typeof listLLMModels;
  invoke: typeof invokeLLM;
};

const DEFAULT_GATEWAY: ModelGateway = { listModels: listLLMModels, invoke: invokeLLM };

const privateIdentifierPatterns = [
  /1[3-9]\d{9}/,
  /(身份证|证件号)/,
  /(微信|wx|wechat|QQ|qq)[：:\s]*[A-Za-z0-9_-]{4,}/,
  /(学校|幼儿园|小学|中学|班级|住址|小区|门牌)/,
];

export function validatePrivateNoteTagInput(input: PrivateNoteTagInput) {
  const text = `${input.title}\n${input.body}`;
  if (!input.privacyAcknowledged) throw new Error("private_note_privacy_acknowledgement_required");
  if (privateIdentifierPatterns.some((pattern) => pattern.test(text))) {
    throw new Error("private_note_contains_identifying_information");
  }
}

function normalizeTags(value: unknown): PrivateNoteTag[] {
  if (!Array.isArray(value)) return [];
  const allowed = new Set<string>(PRIVATE_NOTE_TAGS);
  const selected = value
    .filter((tag): tag is string => typeof tag === "string")
    .map((tag) => tag.trim())
    .filter((tag): tag is PrivateNoteTag => allowed.has(tag));
  return [...new Set(selected)].slice(0, 5);
}

function buildRuleBasedTags(input: PrivateNoteTagInput): PrivateNoteTag[] {
  const text = `${input.title} ${input.body} ${input.topic}`;
  const matches: PrivateNoteTag[] = [];
  const add = (tag: PrivateNoteTag) => { if (!matches.includes(tag)) matches.push(tag); };
  if (/沟通|倾听|对话|回应/.test(text)) add("亲子沟通");
  if (/阅读|绘本|共读|故事/.test(text)) add("家庭阅读");
  if (/学习|作业|习惯|专注/.test(text)) add("学习习惯");
  if (/情绪|生气|难过|陪伴|感受/.test(text)) add("情绪陪伴");
  if (/反思|复盘|观察|调整/.test(text)) add("家庭反思");
  if (/营|21 天|课程/.test(text)) add("成长营");
  add("日常行动");
  return matches.slice(0, 5);
}

export async function suggestPrivateNoteTags(input: PrivateNoteTagInput, gateway: ModelGateway = DEFAULT_GATEWAY): Promise<PrivateNoteTagSuggestion> {
  validatePrivateNoteTagInput(input);
  const fallback = buildRuleBasedTags(input);
  try {
    const catalog = await gateway.listModels();
    const model = catalog.data.find((item) => item.id === "gpt-5-mini")?.id ?? catalog.data.find((item) => item.id.startsWith("gpt-5-"))?.id;
    if (!model) throw new Error("private_note_tag_model_unavailable");
    const result = await gateway.invoke({
      model,
      maxTokens: 180,
      response_format: { type: "json_object" },
      messages: [
        {
          role: "system",
          content: `你只协助给家庭私有小记做可编辑分类。只从以下标签中选择 2 到 5 个：${PRIVATE_NOTE_TAGS.join("、")}。不要输出诊断、能力判断、效果结论、孩子身份信息、评分或解释。只返回 JSON：{"tags":["标签"]}。`,
        },
        {
          role: "user",
          content: JSON.stringify({ title: input.title, body: input.body, topic: input.topic }),
        },
      ],
    });
    const content = result.choices[0]?.message.content;
    const parsed = typeof content === "string" ? JSON.parse(content) as { tags?: unknown } : {};
    const tags = normalizeTags(parsed.tags);
    if (tags.length === 0) throw new Error("private_note_tag_model_empty");
    return {
      tags,
      source: "MODEL_GATEWAY",
      modelGatewayStatus: "INVOKED",
      persistence: "NONE",
      externalEffect: false,
      factBoundary: "TAGS_ARE_EDITABLE_PERSPECTIVE_NOT_FACT",
    };
  } catch {
    return {
      tags: fallback,
      source: "RULE_BASED_FALLBACK",
      modelGatewayStatus: "FALLBACK_RULE_BASED",
      persistence: "NONE",
      externalEffect: false,
      factBoundary: "TAGS_ARE_EDITABLE_PERSPECTIVE_NOT_FACT",
    };
  }
}
