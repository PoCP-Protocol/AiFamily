import { describe, expect, it } from "vitest";

import {
  assessmentDimensionCaption,
  buildAssessmentDimensionProfiles,
  getAssessmentKnowledgeBrief,
} from "../lib/family/assessment-dimension-profile";

describe("family assessment observation profile", () => {
  it("maps the five dimensions without turning observations into a score", () => {
    const profiles = buildAssessmentDimensionProfiles(
      [
        { item_ref: "LEARNING_HABITS_Q01", response_value: "OFTEN" },
        { item_ref: "EMOTION_REGULATION_Q01", response_value: "SOMETIMES" },
        { item_ref: "PARENT_CHILD_COMMUNICATION_Q01", response_value: "RARELY" },
        { item_ref: "DEVICE_USE_CONTEXT_Q01", response_value: "NOT_SURE" },
      ],
      "LEARNING_HABITS",
    );

    expect(profiles).toHaveLength(5);
    expect(profiles.map((profile) => profile.title)).toEqual([
      "学习习惯",
      "情绪管理",
      "亲子沟通",
      "手机依赖",
      "自律能力",
    ]);
    expect(profiles[0]).toMatchObject({
      statusTone: "focus",
      explored: true,
      deepAnsweredCount: 0,
    });
    expect(profiles[1]).toMatchObject({ statusTone: "watch", explored: true });
    expect(profiles[2]).toMatchObject({ statusTone: "quiet", explored: true });
    expect(profiles[3]).toMatchObject({ statusLabel: "信息还不够", explored: false });
    expect(profiles[4]).toMatchObject({ statusLabel: "待了解", explored: false });
    expect(assessmentDimensionCaption(profiles)).toContain("已看见 3 个方向");
  });

  it("normalizes local answers and marks a selected direction as explored deeper", () => {
    const profiles = buildAssessmentDimensionProfiles(
      [
        { item_ref: "LEARNING_HABITS_Q01", response_value: "often" },
        { item_ref: "LEARNING_HABITS_Q02", response_value: "sometimes" },
        { item_ref: "LEARNING_HABITS_Q03", response_value: "not_sure" },
      ],
      "LEARNING_HABITS",
    );

    expect(profiles[0].statusLabel).toContain("深入 2 题");
    expect(profiles[0].signalValue).toBeGreaterThan(0.8);
    expect(profiles[0].statusLabel).not.toContain("分");
  });

  it("keeps knowledge grounding close to the family-facing explanation", () => {
    const brief = getAssessmentKnowledgeBrief("PARENT_CHILD_COMMUNICATION");

    expect(brief).toMatchObject({ title: "亲子沟通" });
    expect(brief?.familyLens).toContain("愿意说");
    expect(brief?.evidence).toContain("CASEL SEL");
    expect(brief?.practiceThemes.length).toBe(3);
  });
});
