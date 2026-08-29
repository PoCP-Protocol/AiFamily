export type FamilyTab = "today" | "growth" | "discover" | "services" | "mine";
export type FamilyLoop = "成长" | "计划" | "评估" | "服务" | "商业" | "社区";

export interface FamilyScreenDefinition {
  id: `UI-${string}`;
  title: string;
  subtitle: string;
  tab: FamilyTab;
  loop: FamilyLoop;
  featurePoints: string[];
  primaryAction: string;
  primaryTarget?: `UI-${string}`;
  baseline: string;
}

export const FAMILY_SCREENS: FamilyScreenDefinition[] = [
  { id: "UI-01", title: "家庭成长首页", subtitle: "看见我们家今天最值得做的一件事", tab: "today", loop: "成长", featurePoints: ["今晚一件事", "当前成长旅程", "最近家庭里程碑", "21 天成长营入口"], primaryAction: "查看今日任务", primaryTarget: "UI-09", baseline: "core-01-home" },
  { id: "UI-02", title: "家庭测评", subtitle: "从真实家庭场景找到当前关注点", tab: "growth", loop: "评估", featurePoints: ["沟通与冲突", "学习与习惯", "手机与边界", "家长视角说明"], primaryAction: "开始选择场景", primaryTarget: "UI-02-result", baseline: "core-02-assessment" },
  { id: "UI-03", title: "AI成长诊断", subtitle: "免费测评的 AI 升级版：综合评估、核心问题与成长建议", tab: "growth", loop: "评估", featurePoints: ["综合成长评估", "核心问题", "成长建议", "个性化方案"], primaryAction: "生成个性化方案", primaryTarget: "UI-04", baseline: "core-03-ai-report" },
  { id: "UI-04", title: "90 天成长方案", subtitle: "四个阶段，一步一步形成家庭新节奏", tab: "growth", loop: "计划", featurePoints: ["看见与理解", "家长先行动", "亲子共同练习", "稳定与复盘"], primaryAction: "查看陪跑安排", primaryTarget: "UI-05", baseline: "core-04-growth-plan" },
  { id: "UI-05", title: "90 天陪跑", subtitle: "任务、家庭小会与阶段回顾在这里汇合", tab: "growth", loop: "计划", featurePoints: ["本周任务", "阶段复盘", "陪伴记录", "家长社群"], primaryAction: "查看今日任务", primaryTarget: "UI-09", baseline: "core-05-delivery-community" },
  { id: "UI-06", title: "我的会员", subtitle: "清楚查看成长权益与服务有效期", tab: "mine", loop: "商业", featurePoints: ["当前方案", "成长权益", "服务额度", "有效期"], primaryAction: "查看年度方案", primaryTarget: "UI-30", baseline: "core-06-mine-member" },
  { id: "UI-07", title: "成长测评入口", subtitle: "选择适合当前家庭阶段的测评", tab: "growth", loop: "评估", featurePoints: ["推荐测评", "预计用时", "同意说明", "历史记录"], primaryAction: "进入家庭测评", primaryTarget: "UI-02", baseline: "growth-01-assessment-entry" },
  { id: "UI-08", title: "家庭过程回顾", subtitle: "回看行动、观察与反思的来源", tab: "growth", loop: "评估", featurePoints: ["过程记录", "观察方向", "证据来源", "需要进一步确认的内容"], primaryAction: "查看可选支持方案", primaryTarget: "UI-04", baseline: "growth-02-ai-report" },
  { id: "UI-09", title: "今日成长任务", subtitle: "今晚只做一件小事", tab: "today", loop: "成长", featurePoints: ["为什么做", "今晚做什么", "可以怎么说", "完成与反思"], primaryAction: "开始这次行动", baseline: "growth-03-daily-task" },
  { id: "UI-10", title: "孩子成长小助手", subtitle: "让孩子以自己的方式表达和选择", tab: "today", loop: "成长", featurePoints: ["孩子友好练习", "表达选择", "可见性说明", "需要帮助"], primaryAction: "看看今天的练习", baseline: "growth-04-child-assistant" },
  { id: "UI-11", title: "我们的成长节奏", subtitle: "只和自己的过去比较", tab: "growth", loop: "成长", featurePoints: ["本周参与", "阶段节奏", "暂停与恢复", "自己的变化"], primaryAction: "查看阶段回顾", primaryTarget: "UI-08", baseline: "growth-05-family-ranking-safe-alternative" },
  { id: "UI-12", title: "成长故事卡", subtitle: "把值得记住的家庭时刻保存下来", tab: "growth", loop: "社区", featurePoints: ["家庭里程碑", "私有保存", "分享草稿", "家庭确认"], primaryAction: "查看家庭小记", primaryTarget: "UI-28", baseline: "growth-06-growth-poster" },
  { id: "UI-13", title: "家庭成长商城", subtitle: "按家庭需要发现课程、工具和服务", tab: "discover", loop: "商业", featurePoints: ["按场景查找", "课程与工具", "会员与服务", "已有权益"], primaryAction: "查看推荐方案", primaryTarget: "UI-14", baseline: "commerce-01-mall-home" },
  { id: "UI-14", title: "成长方案详情", subtitle: "先了解适用场景、投入和交付内容", tab: "discover", loop: "商业", featurePoints: ["适用家庭", "交付内容", "预计投入", "证据边界"], primaryAction: "保存方案意向", primaryTarget: "UI-32", baseline: "commerce-02-product-detail" },
  { id: "UI-15", title: "邀请有礼", subtitle: "把有帮助的成长内容分享给朋友", tab: "discover", loop: "商业", featurePoints: ["单层邀请", "成长权益", "隐私提示", "邀请记录"], primaryAction: "创建邀请草稿", baseline: "commerce-03-invite" },
  { id: "UI-16", title: "家庭同行计划", subtitle: "和熟悉的家庭一起开始成长练习", tab: "discover", loop: "商业", featurePoints: ["同行意向", "参与规则", "家庭人数", "取消与恢复"], primaryAction: "保存参与意向", baseline: "commerce-04-group-buy" },
  { id: "UI-17", title: "成长积分", subtitle: "看见学习、行动与服务积累的权益", tab: "discover", loop: "商业", featurePoints: ["积分任务", "权益账本", "已领取", "规则说明"], primaryAction: "查看积分任务", baseline: "commerce-05-points-task" },
  { id: "UI-18", title: "会员中心", subtitle: "管理会员权益与服务入口", tab: "mine", loop: "商业", featurePoints: ["会员状态", "可用权益", "服务入口", "续费意向"], primaryAction: "查看年度陪伴", primaryTarget: "UI-30", baseline: "commerce-06-mine-member" },
  { id: "UI-19", title: "名师专区", subtitle: "按家庭需要找到适合的专家支持", tab: "services", loop: "服务", featurePoints: ["专家主题", "服务方式", "可用性", "选择说明"], primaryAction: "查看名师详情", primaryTarget: "UI-20", baseline: "teacher-zone" },
  { id: "UI-20", title: "名师详情", subtitle: "了解专业背景、适用场景和服务边界", tab: "services", loop: "服务", featurePoints: ["专业背景", "适用问题", "服务边界", "可预约时段"], primaryAction: "填写咨询需求", primaryTarget: "UI-21", baseline: "teacher-detail" },
  { id: "UI-21", title: "在线咨询预约", subtitle: "先保存家庭需求和时间偏好", tab: "services", loop: "服务", featurePoints: ["需求草稿", "时间偏好", "家庭同意", "提交回执"], primaryAction: "保存咨询意向", primaryTarget: "UI-24", baseline: "consultation-booking" },
  { id: "UI-22", title: "沙龙活动", subtitle: "发现适合当前阶段的家庭成长活动", tab: "services", loop: "服务", featurePoints: ["线上活动", "线下沙龙", "主题筛选", "时间安排"], primaryAction: "查看活动详情", primaryTarget: "UI-23", baseline: "salon-list" },
  { id: "UI-23", title: "活动详情", subtitle: "了解议程、讲师和适用家庭", tab: "services", loop: "服务", featurePoints: ["活动议程", "讲师介绍", "适用对象", "活动意向"], primaryAction: "保存活动意向", primaryTarget: "UI-24", baseline: "activity-detail" },
  { id: "UI-24", title: "我的咨询与活动", subtitle: "回看服务意向、安排和完成记录", tab: "services", loop: "服务", featurePoints: ["待确认", "已安排", "已完成", "后续记录"], primaryAction: "查看服务记录", primaryTarget: "UI-34", baseline: "service-mine" },
  { id: "UI-25", title: "家长社区", subtitle: "交流真实家庭场景中的行动与反思", tab: "discover", loop: "社区", featurePoints: ["主题内容", "阶段群", "经审核经验", "收藏"], primaryAction: "写一篇家庭小记", primaryTarget: "UI-26", baseline: "parent-community" },
  { id: "UI-26", title: "发布家庭小记", subtitle: "先保存私有草稿，再决定是否分享", tab: "discover", loop: "社区", featurePoints: ["私有草稿", "去标识化提示", "可见性", "审核状态"], primaryAction: "保存小记草稿", primaryTarget: "UI-28", baseline: "publish-dynamic" },
  { id: "UI-27", title: "家庭小记详情", subtitle: "区分作者视角、评论观点与可核验事实", tab: "discover", loop: "社区", featurePoints: ["作者视角", "互动评论", "事实来源", "可见性"], primaryAction: "返回家长社区", primaryTarget: "UI-25", baseline: "dynamic-detail" },
  { id: "UI-28", title: "我的社区", subtitle: "管理私有小记、草稿和已发布内容", tab: "discover", loop: "社区", featurePoints: ["私有小记", "待发布草稿", "已发布内容", "收藏"], primaryAction: "写一篇家庭小记", primaryTarget: "UI-26", baseline: "my-community" },
  { id: "UI-29", title: "成长成果", subtitle: "用过程证据和里程碑回看家庭变化", tab: "growth", loop: "评估", featurePoints: ["过程证据", "家庭里程碑", "阶段报告", "来源说明"], primaryAction: "查看家庭档案", primaryTarget: "UI-33", baseline: "growth-outcomes" },
  { id: "UI-30", title: "年度陪伴方案", subtitle: "查看长期陪伴节奏、权益和续费意向", tab: "mine", loop: "商业", featurePoints: ["年度计划", "会员权益", "积分与邀请", "续费意向"], primaryAction: "查看订单与资产", primaryTarget: "UI-32", baseline: "annual-member-mine" },
  { id: "UI-31", title: "我的服务", subtitle: "统一查看课程、计划、专家和活动", tab: "services", loop: "服务", featurePoints: ["进行中服务", "待处理", "已完成", "下一步"], primaryAction: "查看服务记录", primaryTarget: "UI-34", baseline: "my-services" },
  { id: "UI-32", title: "订单与资产", subtitle: "回看意向、权益、报告和家庭资产", tab: "mine", loop: "商业", featurePoints: ["方案意向", "已激活权益", "成长报告", "课程资产"], primaryAction: "查看会员中心", primaryTarget: "UI-18", baseline: "orders-assets" },
  { id: "UI-33", title: "家庭档案", subtitle: "管理家庭成员、角色、同意和成长重点", tab: "mine", loop: "成长", featurePoints: ["家庭成员", "角色与同意", "可见性", "成长重点"], primaryAction: "查看成长成果", primaryTarget: "UI-29", baseline: "family-profile" },
  { id: "UI-34", title: "服务记录", subtitle: "区分服务发生、顾问记录与家长反馈", tab: "services", loop: "服务", featurePoints: ["服务发生记录", "顾问记录", "家长反馈", "来源与时间"], primaryAction: "返回我的服务", primaryTarget: "UI-31", baseline: "service-records" },
];

export function getScreensForTab(tab: FamilyTab) {
  return FAMILY_SCREENS.filter((screen) => screen.tab === tab);
}

export function getFamilyScreen(id: string) {
  return FAMILY_SCREENS.find((screen) => screen.id === id);
}
