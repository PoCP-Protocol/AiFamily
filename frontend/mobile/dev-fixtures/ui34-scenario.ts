import { FAMILY_SCREENS } from "../lib/family/ui-registry";

export type UiFixtureId = `UI-${string}`;

export interface UiScenarioFixture {
  uiId: UiFixtureId;
  state: UiFixtureState;
  headline: string;
  facts: readonly string[];
  nextAction: string;
  fixtureOnly: true;
  externalEffect: false;
}

export type UiFixtureState = "READY" | "DRAFT" | "REVIEW";
export type UiFixtureFilter = UiFixtureState | "ALL";

const FIXTURE_DETAILS: Record<UiFixtureId, Omit<UiScenarioFixture, "uiId" | "fixtureOnly" | "externalEffect">> = {
  "UI-01": { state: "READY", headline: "今晚先完整听孩子说一分钟", facts: ["今日任务 1 项", "成长营第 6 天", "最近记录 2 条"], nextAction: "查看今日任务" },
  "UI-02": { state: "DRAFT", headline: "家庭当前更关注亲子沟通", facts: ["已选 1 个关注方向", "深度问题 3/5", "监护人同意待确认"], nextAction: "继续家庭测评" },
  "UI-03": { state: "REVIEW", headline: "沟通节奏可从倾听练习开始", facts: ["5 个维度说明", "3 条来源证据", "非诊断性建议"], nextAction: "人工确认建议" },
  "UI-04": { state: "DRAFT", headline: "90 天计划草案已生成", facts: ["4 个阶段", "每周 3 个小行动", "尚未确认"], nextAction: "确认计划草案" },
  "UI-05": { state: "READY", headline: "本周陪跑进行中", facts: ["任务 5/9", "家庭记录 3 条", "阶段回顾还有 2 天"], nextAction: "完成今日打卡" },
  "UI-06": { state: "READY", headline: "年度陪伴体验方案", facts: ["专家咨询 2 次", "成长报告 1 份", "有效期 128 天"], nextAction: "查看会员权益" },
  "UI-07": { state: "READY", headline: "推荐家庭沟通测评", facts: ["预计 3 分钟", "5 个生活场景", "可随时退出"], nextAction: "开始测评" },
  "UI-08": { state: "READY", headline: "最近两周完成 6 次家庭行动", facts: ["过程记录 6 条", "家长观察 4 条", "待确认观点 1 条"], nextAction: "查看过程回顾" },
  "UI-09": { state: "DRAFT", headline: "先听完一句话再回应", facts: ["预计 10 分钟", "建议话术 1 条", "尚未开始"], nextAction: "开始行动" },
  "UI-10": { state: "READY", headline: "今天用颜色表达心情", facts: ["孩子自主选择", "家庭内可见", "可跳过"], nextAction: "选择一个练习" },
  "UI-11": { state: "READY", headline: "我们的家庭节奏更稳定了", facts: ["本周参与 4 天", "暂停 1 天", "只与过去比较"], nextAction: "查看阶段回顾" },
  "UI-12": { state: "DRAFT", headline: "保存一次耐心倾听的时刻", facts: ["家庭私有", "来源：家长记录", "未公开分享"], nextAction: "保存故事卡" },
  "UI-13": { state: "READY", headline: "按当前家庭需要浏览", facts: ["课程 3 个", "工具 2 个", "服务 2 个"], nextAction: "查看推荐方案" },
  "UI-14": { state: "DRAFT", headline: "亲子沟通微行动方案", facts: ["21 天内容", "每天约 10 分钟", "仅保存意向"], nextAction: "保存方案意向" },
  "UI-15": { state: "DRAFT", headline: "邀请朋友一起练习", facts: ["邀请草稿 1 份", "不含儿童信息", "尚未发送"], nextAction: "编辑邀请草稿" },
  "UI-16": { state: "DRAFT", headline: "3 个熟悉家庭同行", facts: ["参与家庭 3 个", "开始日期待定", "可随时取消"], nextAction: "保存同行意向" },
  "UI-17": { state: "READY", headline: "成长权益积分 320", facts: ["仅开发账本", "不可兑换现金", "无未成年人营销"], nextAction: "查看积分明细" },
  "UI-18": { state: "READY", headline: "家庭陪伴权益可用", facts: ["课程权益 2 个", "咨询额度 2 次", "报告权益 1 份"], nextAction: "查看服务入口" },
  "UI-19": { state: "READY", headline: "可选择 3 位家庭教育专家", facts: ["沟通主题 2 位", "学习习惯 1 位", "均为已准入展示"], nextAction: "查看专家详情" },
  "UI-20": { state: "READY", headline: "林老师 · 亲子沟通方向", facts: ["从业 8 年", "视频或文字咨询", "下个时段周六 10:00"], nextAction: "填写咨询需求" },
  "UI-21": { state: "DRAFT", headline: "咨询需求草稿", facts: ["视频咨询", "周六上午", "不含孩子原始敏感信息"], nextAction: "保存咨询意向" },
  "UI-22": { state: "READY", headline: "本月有 3 场家庭成长活动", facts: ["线上 2 场", "线下 1 场", "亲子沟通主题"], nextAction: "查看活动详情" },
  "UI-23": { state: "DRAFT", headline: "周末家庭沟通沙龙", facts: ["90 分钟", "12 个家庭名额", "仅保存参与意向"], nextAction: "保存活动意向" },
  "UI-24": { state: "READY", headline: "服务安排一目了然", facts: ["待确认 1 项", "已安排 1 项", "已完成 2 项"], nextAction: "查看服务记录" },
  "UI-25": { state: "READY", headline: "家长社区精选 6 条经验", facts: ["亲子沟通 3 条", "家庭阅读 2 条", "学习习惯 1 条"], nextAction: "写家庭小记" },
  "UI-26": { state: "DRAFT", headline: "记录今晚的一次倾听", facts: ["私有草稿", "已去除身份信息", "尚未申请公开"], nextAction: "保存小记草稿" },
  "UI-27": { state: "READY", headline: "一位家长的行动复盘", facts: ["作者观点 1 条", "评论草稿 2 条", "无权威事实结论"], nextAction: "返回社区" },
  "UI-28": { state: "READY", headline: "我的家庭小记", facts: ["私有 4 条", "待发布 1 条", "收藏 3 条"], nextAction: "管理小记" },
  "UI-29": { state: "READY", headline: "用过程证据看见变化", facts: ["家庭里程碑 3 个", "行动记录 12 条", "无总分与排名"], nextAction: "查看家庭档案" },
  "UI-30": { state: "REVIEW", headline: "年度陪伴续期意向", facts: ["剩余 128 天", "权益使用 4/8", "不会自动扣款"], nextAction: "确认续期意向" },
  "UI-31": { state: "READY", headline: "4 项家庭服务进行中", facts: ["课程 1 项", "成长计划 1 项", "专家与活动 2 项"], nextAction: "查看服务记录" },
  "UI-32": { state: "READY", headline: "家庭资产与意向", facts: ["方案意向 2 个", "可用权益 3 个", "成长报告 1 份"], nextAction: "查看会员中心" },
  "UI-33": { state: "REVIEW", headline: "家庭档案等待监护人确认", facts: ["家庭成员 3 位", "有效同意 2 项", "成长重点 1 项"], nextAction: "检查同意状态" },
  "UI-34": { state: "READY", headline: "最近完成 2 次支持服务", facts: ["服务事实 2 条", "顾问观点 1 条", "家长反馈 2 条"], nextAction: "返回我的服务" },
};

export const UI34_SCENARIO_FIXTURES: readonly UiScenarioFixture[] = FAMILY_SCREENS.map((screen) => ({
  uiId: screen.id,
  ...FIXTURE_DETAILS[screen.id],
  fixtureOnly: true,
  externalEffect: false,
}));

export function getUiScenarioFixture(uiId: string) {
  return UI34_SCENARIO_FIXTURES.find((fixture) => fixture.uiId === uiId);
}

export function getUiScenarioFixtureForPathname(pathname: string) {
  if (pathname === "/" || pathname === "/index") return getUiScenarioFixture("UI-01");
  const match = pathname.match(/^\/ui\/(UI-\d{2})(?:\/|$)/);
  return match ? getUiScenarioFixture(match[1]) : undefined;
}

export function getUiScenarioFixtureCounts() {
  return UI34_SCENARIO_FIXTURES.reduce(
    (counts, fixture) => ({ ...counts, [fixture.state]: counts[fixture.state] + 1 }),
    { ALL: UI34_SCENARIO_FIXTURES.length, READY: 0, DRAFT: 0, REVIEW: 0 },
  );
}
