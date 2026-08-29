import type { FamilyLoop } from "./ui-registry";

export type ControlledActionKind = "assessment_draft" | "plan_decision" | "commerce_intent" | "service_intent" | "community_draft" | "profile_update" | "asset_export";

export interface UiActionPolicy {
  screenId: `UI-${string}`;
  loop: FamilyLoop;
  kind: ControlledActionKind;
  receiptMessage: string;
}

export const UI_ACTION_POLICIES: Partial<Record<`UI-${string}`, UiActionPolicy>> = {
  "UI-02": { screenId: "UI-02", loop: "评估", kind: "assessment_draft", receiptMessage: "家庭关注场景已保存为测评草稿。" },
  "UI-04": { screenId: "UI-04", loop: "计划", kind: "plan_decision", receiptMessage: "方案选择已记下，尚未正式启动 90 天计划。" },
  "UI-06": { screenId: "UI-06", loop: "计划", kind: "service_intent", receiptMessage: "本周打卡已保存为家庭私有草稿，未形成服务记录或成长结果。" },
  "UI-12": { screenId: "UI-12", loop: "社区", kind: "community_draft", receiptMessage: "成长故事已保存为家庭私有草稿。" },
  "UI-14": { screenId: "UI-14", loop: "商业", kind: "commerce_intent", receiptMessage: "方案意向已保存；Dev 环境未支付、未扣款。" },
  "UI-15": { screenId: "UI-15", loop: "商业", kind: "commerce_intent", receiptMessage: "邀请草稿已保存，未向任何联系人发送。" },
  "UI-16": { screenId: "UI-16", loop: "商业", kind: "commerce_intent", receiptMessage: "同行计划参与意向已保存，未创建订单。" },
  "UI-17": { screenId: "UI-17", loop: "商业", kind: "commerce_intent", receiptMessage: "积分任务查看记录已保存，未自动发放权益。" },
  "UI-21": { screenId: "UI-21", loop: "服务", kind: "service_intent", receiptMessage: "咨询需求已保存为草稿，未占用时段、未通知专家。" },
  "UI-23": { screenId: "UI-23", loop: "服务", kind: "service_intent", receiptMessage: "活动参与意向已保存，未报名、未外发通知。" },
  "UI-26": { screenId: "UI-26", loop: "社区", kind: "community_draft", receiptMessage: "家庭小记已保存为私有草稿，未公开发布。" },
  "UI-30": { screenId: "UI-30", loop: "商业", kind: "commerce_intent", receiptMessage: "年度陪伴确认意向已保存；Dev 环境仅内部激活，不扣款。" },
  "UI-29": { screenId: "UI-29", loop: "成长", kind: "asset_export", receiptMessage: "成长成果导出预览已生成；未创建文件或外发内容。" },
  "UI-31": { screenId: "UI-31", loop: "服务", kind: "asset_export", receiptMessage: "服务摘要导出预览已生成；未创建文件或外发内容。" },
  "UI-32": { screenId: "UI-32", loop: "商业", kind: "asset_export", receiptMessage: "家庭资产导出预览已生成；未创建文件或外发内容。" },
  "UI-33": { screenId: "UI-33", loop: "成长", kind: "profile_update", receiptMessage: "家庭档案修改已保存为待确认草稿。" },
  "UI-34": { screenId: "UI-34", loop: "服务", kind: "asset_export", receiptMessage: "服务记录导出预览已生成；未创建文件或外发内容。" },
};

export function getUiActionPolicy(screenId: string) {
  return UI_ACTION_POLICIES[screenId as `UI-${string}`];
}
