import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { GROWTH_FOCUSES } from "../lib/family/core-growth";
import { FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY } from "../lib/family/family-assessment-capability-memory";
import { buildUi02AssessmentResultSummary } from "../lib/family/ui02-assessment-design";
import {
  UI02_ASSESSMENT_METHOD_SOURCE,
  UI02_ORIGINAL_FOCUS_LAYOUT,
} from "../lib/family/ui02-assessment-layout";

describe("UI-02 family conversation assessment contract", () => {
  const source = readFileSync(
    resolve(process.cwd(), "app/ui/UI-02.tsx"),
    "utf8",
  );

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

  it("starts from the adult's own words and offers a sandbox voice entry", () => {
    expect(source).toContain("你现在最想解决什么？");
    expect(source).toContain("assessment-need-input");
    expect(source).toContain("assessment-voice-sandbox");
    expect(source).toContain("语音转写只在当前设备完成");
    expect(source).toContain("保存并退出");
  });

  it("explains purpose and asks for one plain-language consent before choices", () => {
    expect(source).toContain("这些信息会怎么用？");
    expect(source).toContain("仅限你的家庭可见");
    expect(source).toContain("你可以随时撤回授权");
    expect(source).toContain("我明白了，继续");
    expect(source).toContain("返回修改来意");
  });

  it("extends the original step with sourced model deep-dive questions", () => {
    expect(FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.blueprint.methodName).toBe(
      "Family Support Assessment",
    );
    expect(FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.blueprint.layer).toBe(
      "L0_FAMILY_NEED_AND_SERVICE_PREFERENCE",
    );
    expect(
      FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.blueprint.stepModel.map(
        (step) => step.stepRef,
      ),
    ).toEqual([
      "CONSENT_AND_BOUNDARY",
      "CURRENT_NEED",
      "SUPPORT_DIRECTION",
      "SERVICE_PREFERENCE",
      "NEXT_DECISION",
    ]);
    expect(
      FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.dimensions.every(
        (dimension) => dimension.questions.length === 3,
      ),
    ).toBe(true);
    expect(source).toContain("getUi02DeepAssessmentQuestions");
    expect(source).toContain("UI02_ASSESSMENT_ANSWER_OPTIONS");
    expect(source).toContain("question.itemRef");
    expect(source).toContain("只问三件小事");
    expect(source).toContain("跳过这一题");
    expect(source).toContain("assessment-question-continue");
  });

  it("builds a structured result summary from the assessment model and saved answers", () => {
    const summary = buildUi02AssessmentResultSummary("LEARNING_HABITS", {
      LEARNING_HABITS_Q01: "OFTEN",
      LEARNING_HABITS_Q02: "SOMETIMES",
      LEARNING_HABITS_Q03: "RARELY",
    });

    expect(summary).toMatchObject({
      title: "学习习惯",
      answeredCount: 3,
      totalCount: 3,
    });
    expect(summary?.observationSignals).toContain(
      "过去两周，孩子开始写作业前常需要反复提醒。",
    );
    expect(summary?.supportDirections).toContain("把作业拆小步");
    expect(summary?.theorySupport.join("\n")).toContain(
      "Harvard Executive Function",
    );
    expect(summary?.familyTheorySupport.join("\n")).toContain("比起反复催促");
    expect(summary?.dataSupport.join("\n")).toContain("不给孩子打分");
    expect(summary?.platformIntegration.businessScenario).toBe(
      "S2_FAMILY_SELF_CHECK_AND_SUPPORT_NEED",
    );
    expect(summary?.platformIntegration.applicationSurfaces).toContain(
      "生成90天陪伴计划",
    );
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
      expect(
        dimension.questions.every(
          (question) =>
            question.intent.length > 8 && question.evidenceAnchor.length > 8,
        ),
      ).toBe(true);
    }

    const allTheorySupport = FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.dimensions
      .flatMap((dimension) => dimension.theorySupport)
      .join("\n");
    expect(allTheorySupport).toContain("Harvard Executive Function");
    expect(allTheorySupport).toContain("CASEL SEL");
    expect(allTheorySupport).toContain("CDC Parenting");
    expect(allTheorySupport).toContain("AAP HealthyChildren Media");
    expect(allTheorySupport).toContain("Family 知识库");
  });

  it("registers the free assessment as part of the family education intelligence platform", () => {
    expect(
      FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.platformIntegration.dataObjects,
    ).toEqual([
      "AssessmentTool",
      "AssessmentSession",
      "AssessmentResponse",
      "FamilyNeed",
      "SupportDirection",
      "ConsentReceipt",
    ]);
    expect(
      FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.platformIntegration.aiBoundary,
    ).toContain("不得生成诊断、总分、排名");
    expect(
      FAMILY_ASSESSMENT_AI_CAPABILITY_MEMORY.platformIntegration
        .improvementLoop,
    ).toContain("完成率");
  });

  it("sources the assessment method from the family education model memory", () => {
    expect(UI02_ASSESSMENT_METHOD_SOURCE.capabilityRef).toBe(
      "FAMILY_ASSESSMENT_AI_CAPABILITY",
    );
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
    expect(source).toContain(
      "ui02-question:${sessionId}:${question.itemRef}:${answer}",
    );
    expect(source).toContain("subject_person_id: subjectId");
    expect(source).toContain("tool_ref: projection.tool.tool_ref");
    expect(source).toContain('router.push("/ui/UI-02-result" as Href)');
    expect(source).not.toContain("SELECT_SYNTHETIC_ASSESSMENT_DIMENSION");
  });

  it("keeps the smallest completion behind the consent boundary", () => {
    expect(source).toContain(
      'const remoteCanStart = !connected || projection?.availability === "AVAILABLE"',
    );
    expect(source).toContain("当前家庭还没有可用的测评授权");
    expect(source).toContain("不会重复创建记录");
    expect(source).toContain("!remoteCanStart");
    expect(source).toContain('projectionState === "loading"');
  });

  it("keeps the commercial consent, evidence, and non-diagnosis boundary explicit", () => {
    expect(source).toContain('projection.availability !== "AVAILABLE"');
    expect(source).toContain('subject.availability === "AVAILABLE"');
    expect(source).toContain("这是家庭自查，不给孩子打分，不做诊断或排名。");
    expect(source).not.toContain("工具版本 v${projection.tool.version_no}");
    expect(source).not.toContain(
      'session.status === "connected" ? "请选择孩子" : "连接家庭后读取"',
    );
    expect(source).not.toContain(">10岁<");

    const resultSource = readFileSync(
      resolve(process.cwd(), "app/ui/UI-02-result.tsx"),
      "utf8",
    );
    expect(resultSource).toContain("我们听到的家庭关注");
    expect(resultSource).toContain("可能的方向");
    expect(resultSource).toContain("还不确定的地方");
    expect(resultSource).toContain("今天可以尝试的一小步");
    expect(resultSource).toContain("查看可解释结果");
    expect(resultSource).toContain('assessmentSyncState === "synced"');
    expect(resultSource).toContain("assessment-local-boundary");
    expect(resultSource).toContain("连上家庭服务后，才会开放服务端回看");
    expect(resultSource).toContain("重新开始测评");
    expect(resultSource).toContain("不是对孩子的评分或诊断");
    expect(resultSource).not.toContain("FAMILY_ASSESSMENT_AI_CAPABILITY");
    expect(resultSource).not.toContain("模型来源");
    expect(resultSource).not.toContain("UI02_ASSESSMENT_METHOD_SOURCE");

    const explanationSource = readFileSync(
      resolve(process.cwd(), "app/ui/UI-03.tsx"),
      "utf8",
    );
    expect(explanationSource).toContain("家庭范围 · 可回读结果");
    expect(explanationSource).toContain("查看本次依据");
    expect(explanationSource).toContain("重新开始测评");
    expect(explanationSource).toContain("退出");
    expect(explanationSource).toContain("不是对孩子的评分、排名或诊断");
  });
});
