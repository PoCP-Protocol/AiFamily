import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  assessmentDimensionCaption,
  buildAssessmentDimensionProfiles,
  getAssessmentKnowledgeBrief,
} from "../lib/family/assessment-dimension-profile";

const componentSource = readFileSync(
  resolve(process.cwd(), "components/family/assessment-dimension-radar.tsx"),
  "utf8",
);

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
    expect(profiles[0].evidenceRefs).toEqual(["LEARNING_HABITS_Q01"]);
    expect(profiles[0].knowledgeRefs[0]).toContain("执行功能");
    expect(profiles[4].unknownText).toContain("不会替家庭猜测");
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

  it("keeps a dimension unknown when the API projection has no evidence", () => {
    const profiles = buildAssessmentDimensionProfiles([], null);

    expect(profiles.every((profile) => profile.evidenceRefs.length === 0)).toBe(true);
    expect(profiles.every((profile) => profile.statusTone === "unknown")).toBe(true);
    expect(profiles.every((profile) => profile.unknownText.includes("不会替家庭猜测"))).toBe(true);
  });

  it("keeps knowledge grounding close to the family-facing explanation", () => {
    const brief = getAssessmentKnowledgeBrief("PARENT_CHILD_COMMUNICATION");

    expect(brief).toMatchObject({ title: "亲子沟通" });
    expect(brief?.familyLens).toContain("愿意说");
    expect(brief?.evidence).toContain("CASEL SEL");
    expect(brief?.practiceThemes.length).toBe(3);
  });

  it("lets a guardian expand evidence, knowledge, and unknowns then save a correction draft", () => {
    expect(componentSource).toContain("查看依据、知识与未知");
    expect(componentSource).toContain("本次依据");
    expect(componentSource).toContain("知识参考");
    expect(componentSource).toContain("还不知道");
    expect(componentSource).toContain("家长修正");
    expect(componentSource).toContain("记下这条修正");
    expect(componentSource).toContain("不会自动改写家庭事实");
    expect(componentSource).not.toMatch(/overall_score|peer_reference|ranking|同伴比较/);
  });
});
