import type { ServiceOfferingDto } from "../../lib/family/service-api-contracts";
import { FamilyApiError } from "../../lib/family/family-api-client";

export interface ServiceCardModel {
  id: string;
  ref: string;
  title: string;
  provider: string;
  summary: string;
  channel: string;
  theme: "COMMUNICATION" | "EMOTION" | "STUDY" | "FAMILY";
  expertise: string[];
  provenance: "REMOTE" | "SYNTHETIC";
  accent: string;
}

export function mapServiceOfferings(offerings: readonly ServiceOfferingDto[] | undefined): ServiceCardModel[] {
  return (offerings ?? []).map((item, index) => {
    const titleValue = `${item.title}${item.provider_display_name}`;
    const theme: ServiceCardModel["theme"] = /学习|习惯/.test(titleValue) ? "STUDY" : /情绪/.test(titleValue) ? "EMOTION" : /家庭|关系/.test(titleValue) ? "FAMILY" : "COMMUNICATION";
    return {
      id: item.service_offering_id,
      ref: item.service_offering_ref,
      title: item.title,
      provider: item.provider_display_name,
      summary: "从家庭当前情境出发，先了解支持方向、适用场景和服务边界。",
      channel: item.channel_options[0] ? channelLabel(item.channel_options[0]) : "方式待确认",
      theme,
      expertise: ["家庭成长", "家庭支持", item.channel_options[0] ? channelLabel(item.channel_options[0]) : "方式待确认"],
      provenance: "REMOTE",
      accent: index % 2 === 0 ? "#16866D" : "#7556C8",
    };
  });
}

export function isServiceAccessDenied(error: unknown) {
  return error instanceof FamilyApiError && (error.status === 401 || error.status === 403 || error.code.includes("CONSENT") || error.code.includes("POLICY"));
}

export function channelLabel(channel: "VIDEO" | "TEXT" | "OFFLINE") {
  return channel === "VIDEO" ? "视频交流" : channel === "TEXT" ? "文字交流" : "线下交流";
}
