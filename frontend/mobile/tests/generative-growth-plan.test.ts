import { describe, expect, it } from "vitest";

import {
  isAdoptedGrowthPlan,
  isGrowthPlanDraft,
  isGrowthPlanInformationNeeded,
  type GenerativeGrowthPlan,
} from "../lib/family/generative-growth-plan";

describe("generative family growth plan scene", () => {
  it("keeps a generated draft adjustable before the parent adopts it", () => {
    const plan = {
      result_status: "PLAN_DRAFT",
      draft_ref: "draft-family-11",
      draft_version: 3,
      title: "把晚间冲突变成可以重新合作的时刻",
      family_goal: { statement: "家长和孩子能在冲突后重新开口", observable_signs: [], evidence_refs: [] },
      why_this_plan: "家庭目前需要先恢复对话，再共同调整手机使用节奏。",
      duration: { days: 28, rationale: "需要跨过四个周末观察不同情境。" },
      stages: [],
      adjustable_choices: [],
      unknowns_to_watch: [],
      review_rhythm: { frequency: "每周", questions: [] },
      limitations: [],
    } satisfies GenerativeGrowthPlan;

    expect(isGrowthPlanDraft(plan)).toBe(true);
    expect(isAdoptedGrowthPlan(plan)).toBe(false);
    expect(plan.duration.days).toBe(28);
  });

  it("continues from an adopted plan instead of asking the parent to adopt twice", () => {
    const plan = {
      plan_id: "plan-family-11",
      tenant_id: "tenant-demo",
      family_id: "family-11",
      subject_refs: ["child-11"],
      draft_ref: "draft-family-11",
      draft_version: 3,
      model_run_ref: "run-11",
      provenance_ref: "provenance-11",
      content_sha256: "a".repeat(64),
      title: "把晚间冲突变成可以重新合作的时刻",
      family_goal: { statement: "家长和孩子能在冲突后重新开口", observable_signs: [], evidence_refs: [] },
      why_this_plan: "先恢复对话，再共同调整节奏。",
      duration: { days: 28, rationale: "跨四周观察。" },
      stages: [],
      adjustable_choices: [],
      selected_choices: { rhythm: "每周两次" },
      unknowns_to_watch: [],
      review_rhythm: { frequency: "每周", questions: [] },
      limitations: [],
      status: "ACTIVE",
      adopted_by: "guardian-11",
      adopted_at: "2026-09-04T08:00:00Z",
      boundary: "HUMAN_ADOPTED_GENERATIVE_DRAFT_NOT_AI_CREATED_FACT",
    } satisfies GenerativeGrowthPlan;

    expect(isAdoptedGrowthPlan(plan)).toBe(true);
    expect(isGrowthPlanDraft(plan)).toBe(false);
    expect(plan.selected_choices).toEqual({ rhythm: "每周两次" });
  });

  it("keeps asking for context when the model cannot yet produce a useful plan", () => {
    const plan = {
      result_status: "NEEDS_MORE_INFORMATION",
      information_needed: ["冲突通常发生在什么时间？"],
      known_context_summary: "家长希望减少晚间冲突。",
      limitations: ["还不了解孩子当时正在做什么"],
    } satisfies GenerativeGrowthPlan;

    expect(isGrowthPlanInformationNeeded(plan)).toBe(true);
    expect(isGrowthPlanDraft(plan)).toBe(false);
  });
});
