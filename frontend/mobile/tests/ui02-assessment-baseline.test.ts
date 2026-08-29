import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { GROWTH_FOCUSES } from "../lib/family/core-growth";
import { FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY } from "../lib/family/family-assessment-capability-memory";
import { buildUi02AssessmentResultSummary } from "../lib/family/ui02-assessment-design";
import { UI02_ASSESSMENT_METHOD_SOURCE, UI02_ORIGINAL_FOCUS_LAYOUT } from "../lib/family/ui02-assessment-layout";

describe("UI-02 original step-two assessment contract", () => {
  const source = readFileSync(resolve(process.cwd(), "app/ui/UI-02.tsx"), "utf8");

  it("keeps the original five single-choice focus areas", () => {
    expect(GROWTH_FOCUSES).toHaveLength(5);
    expect(UI02_ORIGINAL_FOCUS_LAYOUT.map((focus) => focus.title)).toEqual([
      "学习习惯",
      "情绪管理",
      "亲子沟通",
      "手机依赖",
      "自律能力",
    ]);
    expect(UI02_ORIGINAL_FOCUS_LAYOUT.map((focus) => focus.id).sort()).toEqual([
      "DEVICE_USE_CONTEXT",
      "EMOTION_REGULATION",
      "LEARNING_HABITS",
      "PARENT_CHILD_COMMUNICATION",
      "SELF_REGULATION",
    ]);
    expect(source).toContain('accessibilityRole="radio"');
  });

  it("keeps the original step, optional supplement, and next-action structure", () => {
    expect(source).toContain("第 2 / 5 步");
    expect(source).toContain("最近最想先支持孩子的哪一方面？");
    expect(source).toContain("请选择最贴近最近情况的一项。");
    expect(source).toContain("再了解一点");
    expect(source).toContain("服务偏好");
    expect(source).toContain("补充信息");
    expect(source).toContain("孩子年龄/阶段");
    expect(source).toContain("家庭情况");
    expect(source).toContain("孩子性别");
    expect(source).toContain('"下一步"');
  });

  it("keeps the age/stage field as an explicit selectable dropdown", () => {
    expect(source).toContain("const CHILD_STAGE_OPTIONS");
    expect(source).toContain("setChildStageOpen((value) => !value)");
    expect(source).toContain('accessibilityState={{ expanded: childStageOpen }}');
    expect(source).toContain("CHILD_STAGE_OPTIONS.map");
    expect(source).toContain("setChildStage(option)");
    expect(source).toContain("setChildStageOpen(false)");
    expect(source).toContain("3岁（学龄前）");
    expect(source).toContain("16岁及以上（高中及以上）");
  });

  it("extends the original step with sourced model deep-dive questions", () => {
    expect(FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.blueprint.methodName).toBe("Family Support Assessment");
    expect(FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.blueprint.layer).toBe("L0_FAMILY_NEED_AND_SERVICE_PREFERENCE");
    expect(FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.blueprint.stepModel.map((step) => step.stepRef)).toEqual([
      "CONSENT_AND_BOUNDARY",
      "CURRENT_NEED",
      "SUPPORT_DIRECTION",
      "SERVICE_PREFERENCE",
      "NEXT_DECISION",
    ]);
    expect(FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.dimensions.every((dimension) => dimension.questions.length === 3)).toBe(true);
    expect(source).toContain("getUi02DeepAssessmentQuestions");
    expect(source).toContain("UI02_ASSESSMENT_ANSWER_OPTIONS");
    expect(source).toContain("question.itemRef");
    expect(source).toContain("answerAssessment(question.itemRef, option.id)");
  });

  it("builds a structured result summary from the assessment model and saved answers", () => {
    const summary = buildUi02AssessmentResultSummary("LEARNING_HABITS", {
      LEARNING_HABITS_Q01: "OFTEN",
      LEARNING_HABITS_Q02: "SOMETIMES",
      LEARNING_HABITS_Q03: "RARELY",
    });

    expect(summary).toMatchObject({ title: "学习习惯", answeredCount: 3, totalCount: 3 });
    expect(summary?.observationSignals).toContain("过去两周，孩子开始写作业前常需要反复提醒。");
    expect(summary?.supportDirections).toContain("把作业拆小步");
    expect(summary?.theorySupport.join("\n")).toContain("Harvard Executive Function");
    expect(summary?.familyTheorySupport.join("\n")).toContain("比起反复催促");
    expect(summary?.dataSupport.join("\n")).toContain("不给孩子打分");
    expect(summary?.platformIntegration.businessScenario).toBe("S2_FAMILY_SELF_CHECK_AND_SUPPORT_NEED");
    expect(summary?.platformIntegration.applicationSurfaces).toContain("生成90天陪伴计划");
    expect(summary?.boundary).toContain("不推断智力");
  });

  it("requires each of the five themes to carry theory, data, practice support, and boundaries", () => {
    for (const dimension of FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.dimensions) {
      expect(dimension.operationalDefinition.length).toBeGreaterThan(10);
      expect(dimension.theorySupport.length).toBeGreaterThanOrEqual(2);
      expect(dimension.familyTheorySupport.length).toBeGreaterThanOrEqual(2);
      expect(dimension.dataSupport.length).toBeGreaterThanOrEqual(3);
      expect(dimension.practiceSupport.length).toBeGreaterThanOrEqual(3);
      expect(dimension.observableSignals.length).toBe(3);
      expect(dimension.nextSupportDirections.length).toBeGreaterThanOrEqual(3);
      expect(dimension.boundary).toMatch(/不|不能/);
      expect(dimension.questions.every((question) => question.intent.length > 8 && question.evidenceAnchor.length > 8)).toBe(true);
    }

    const allTheorySupport = FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.dimensions.flatMap((dimension) => dimension.theorySupport).join("\n");
    expect(allTheorySupport).toContain("Harvard Executive Function");
    expect(allTheorySupport).toContain("CASEL SEL");
    expect(allTheorySupport).toContain("CDC Parenting");
    expect(allTheorySupport).toContain("AAP HealthyChildren Media");
    expect(allTheorySupport).toContain("Family 知识库");
  });

  it("registers the free assessment as part of the family education intelligence platform", () => {
    expect(FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.platformIntegration.dataObjects).toEqual([
      "AssessmentTool",
      "AssessmentSession",
      "AssessmentResponse",
      "FamilyNeed",
      "SupportDirection",
      "ConsentReceipt",
    ]);
    expect(FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.platformIntegration.aiBoundary).toContain("不得生成诊断、总分、排名");
    expect(FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.platformIntegration.improvementLoop).toContain("完成率");
  });

  it("sources the assessment method from the family education model memory", () => {
    expect(UI02_ASSESSMENT_METHOD_SOURCE.capabilityRef).toBe("FAMILY_ASSESSMENT_AI_CAPABILITY");
    expect(UI02_ASSESSMENT_METHOD_SOURCE.toolRef).toBe("FAMILY_SUPPORT_NEEDS");
    expect(UI02_ASSESSMENT_METHOD_SOURCE.boundary.notScore).toBe(true);
    expect(UI02_ASSESSMENT_METHOD_SOURCE.boundary.notDiagnosis).toBe(true);
    expect(source).not.toContain("Family Support Assessment ·");
    expect(source).not.toContain("L0_FAMILY_NEED_AND_SERVICE_PREFERENCE");
    expect(source).not.toContain("Need/Intent");
    expect(source).not.toContain("家庭教育模型测评题库");
    expect(source).not.toContain("方向深追题");
    expect(source).not.toContain("question.intent");
  });

  it("submits the versioned assessment before entering the assessment result page", () => {
    expect(source).toContain("getFamilyAssessment");
    expect(source).toContain("startFamilyAssessment");
    expect(source).toContain("saveFamilyAssessmentResponse");
    expect(source).toContain("submitFamilyAssessment");
    expect(source).toContain("ui02-deep:${sessionId}:${question.itemRef}:${answer}");
    expect(source).toContain("subject_person_id: subjectId");
    expect(source).toContain("tool_ref: projection.tool.tool_ref");
    expect(source).toContain('router.push("/ui/UI-02-result" as Href)');
    expect(source).not.toContain("SELECT_SYNTHETIC_ASSESSMENT_DIMENSION");
  });

  it("does not allow next step until the family boundary and all selected deep questions are complete", () => {
    expect(source).toContain("answeredQuestionCount === selectedQuestions.length");
    expect(source).toContain("boundaryAccepted && !!selectedGrowthFocus && answeredQuestionCount === selectedQuestions.length");
    expect(source).toContain("请先确认。");
    expect(source).toContain("请完成补充问题。");
    expect(source).toContain('disabled={!canSubmitAssessment || assessmentSyncState === "syncing"');
  });

  it("keeps the commercial consent, evidence, and non-diagnosis boundary explicit", () => {
    expect(source).toContain('projection.availability !== "AVAILABLE"');
    expect(source).toContain('subject.availability === "AVAILABLE"');
    expect(source).toContain("我知道这只是家庭自查，不给孩子打分，不做诊断或排名。");
    expect(source).not.toContain("工具版本 v${projection.tool.version_no}");
    expect(source).not.toContain('session.status === "connected" ? "请选择孩子" : "连接家庭后读取"');
    expect(source).not.toContain('>10岁<');

    const resultSource = readFileSync(resolve(process.cwd(), "app/ui/UI-02-result.tsx"), "utf8");
    expect(resultSource).toContain("免费家庭测评已完成");
    expect(resultSource).toContain("这次看见了什么");
    expect(resultSource).toContain("为什么这样建议");
    expect(resultSource).toContain("这次看到的情况");
    expect(resultSource).toContain("接下来可以继续");
    expect(resultSource).toContain("buildUi02AssessmentResultSummary");
    expect(resultSource).toContain("返回调整免费测评");
    expect(resultSource).toContain("升级到 AI 成长诊断，看更完整的分析");
    expect(resultSource).toContain("不是对孩子的评分、排名或诊断");
    expect(resultSource).not.toContain("FAMILY_ASSESSMENT_AI_CAPABILITY");
    expect(resultSource).not.toContain("模型来源");
    expect(resultSource).not.toContain("UI02_ASSESSMENT_METHOD_SOURCE");

    const explanationSource = readFileSync(resolve(process.cwd(), "app/ui/UI-03.tsx"), "utf8");
    expect(explanationSource).toContain("AI成长诊断");
    expect(explanationSource).toContain("综合成长评估");
    expect(explanationSource).toContain("生成个性化方案");
    expect(explanationSource).toContain("不是儿童诊断结论、能力测验或排名");
  });
});
