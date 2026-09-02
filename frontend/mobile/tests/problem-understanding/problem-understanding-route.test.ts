import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const route = readFileSync(
  resolve(process.cwd(), "app/family/problem-understanding.tsx"),
  "utf8",
);
const components = readFileSync(
  resolve(process.cwd(), "features/problem-understanding/components.tsx"),
  "utf8",
);
const controller = readFileSync(
  resolve(process.cwd(), "features/problem-understanding/controller.ts"),
  "utf8",
);
const rootLayout = readFileSync(
  resolve(process.cwd(), "app/_layout.tsx"),
  "utf8",
);

describe("Problem Understanding standalone Expo route", () => {
  it("composes the reusable experience inside the established platform shell", () => {
    expect(route).toContain("ConcernComposer");
    expect(route).toContain("UnderstandingMap");
    expect(route).toContain("CorrectionConfirmation");
    expect(route).toContain("RecoveryNotice");
    expect(route).toContain('backgroundColor: "#FFF9F5"');
    expect(rootLayout).toContain("<ResponsivePlatformShell>");
  });

  it("uses only the real S3 multimodal HTTP response at runtime", () => {
    expect(route).toContain("familyApi.createMultimodalUnderstandingDraft");
    expect(route).toContain("buildMultimodalDraftRequest");
    expect(route).toContain("toUnderstandingDraft");
    expect(route).toContain("familyApi.decideMultimodalUnderstandingRun");
    expect(route).toContain("familyApi.requestMultimodalHumanReview");
    expect(route).toContain("familyApi.deleteMultimodalUnderstandingRun");
    expect(route).toContain("replayMultimodalUnderstandingRun");
    expect(route).toContain("选择测试图片（仅沙盒）");
    expect(route).toContain("asset:sandbox/family-homework-transition-v1");
    expect(route).toContain('process.env.NODE_ENV !== "production"');
    expect(route).not.toContain("createSyntheticUnderstanding");
    expect(route).not.toContain("createSyntheticReceipt");
    expect(route).not.toContain("DEV_SYNTHETIC_PROBLEM_UNDERSTANDING");
  });

  it("does not expose internal implementation language in visible copy", () => {
    expect(route).not.toMatch(
      />\s*(DEV|SYNTHETIC|DTO|GrowthCase|provenance)\s*</,
    );
    expect(route).not.toContain("overall_score");
    expect(route).not.toContain("peer_reference");
    expect(route).not.toContain("默认50");
  });

  it("offers a complete human-readable feedback, exit, server delete, and restore path", () => {
    expect(route).toContain("AsyncStorage.getItem");
    expect(route).toContain("AsyncStorage.setItem");
    expect(route).toContain("AsyncStorage.removeItem");
    expect(route).toContain("继续这次对话");
    expect(route).toContain("删除已保存内容");
    const deleteHandler = route.slice(
      route.indexOf("const handleDelete"),
      route.indexOf("const handleStartNew"),
    );
    expect(
      deleteHandler.indexOf("deleteMultimodalUnderstandingRun"),
    ).toBeLessThan(
      deleteHandler.indexOf("AsyncStorage.removeItem(STORAGE_KEY)"),
    );
    expect(route).toContain("内容仍然保留");
    expect(route).toContain("刷新后也不会恢复");
    expect(route).toContain("正在找回你上次保存的内容");
    expect(route).toContain("家庭服务暂时没有连接");
    expect(route).toContain("重新连接");
    expect(route).toContain("session.connectDevSession()");
    expect(route).toContain("onSkipClarification");
    expect(route).toContain("onSaveAndExit");
    expect(components).toContain("你说的");
    expect(components).toContain("我们的理解");
    expect(controller).toContain("还不确定");
    expect(controller).toContain("对，就是这样");
    expect(components).toContain("有点不对");
    expect(components).toContain("我想补充");
    expect(components).toContain("先跳过澄清");
    expect(components).toContain("退出并保存");
    expect(components).toContain("请人工帮我看看");
    expect(components).toContain("删除这次内容");
    expect(components).toContain("这份理解从哪里来");
    expect(components).toContain("几种值得一起验证的理解");
    expect(components).toContain("我这样理解，是因为你提到");
    expect(components).toContain("什么信息会改变这个判断");
    expect(components).toContain("你们已经拥有的力量");
    expect(components).toContain("回答这个问题 →");
    expect(route).toContain("handleAnswerQuestion");
    expect(route).toContain("onAnswerQuestion={handleAnswerQuestion}");
  });

  it("uses one clear three-step promise and adapts review density by viewport", () => {
    expect(route).toContain("今天，想先把哪件事说清楚？");
    expect(route).toContain("1 说出困扰");
    expect(route).toContain("2 确认理解");
    expect(route).toContain("3 继续深入理解");
    expect(route).not.toContain("3 获得下一步");
    expect(route).not.toContain("获得下一步");
    expect(route).toContain("useWindowDimensions");
    expect(route).toContain("width < 480");
    expect(route).toContain("width >= 960");
    expect(route).toContain("reviewWidth >= 760");
    expect(route).toContain("event.nativeEvent.layout.width");
    expect(route).toContain("reviewLayoutWide");
    expect(route).toContain("maxWidth: 1180");
    expect(components).toContain("这份理解准确吗？");
    expect(components).toContain("不会自动改变家庭记录");
  });

  it("lets the adult add context or start a new understanding after confirmation", () => {
    expect(route).toContain('state.phase === "CONFIRMED"');
    expect(route).toContain("已记下你的反馈");
    expect(route).toContain("补充新情况");
    expect(route).toContain("开始新的理解");
    expect(route).not.toContain("选一个彼此都不赶时间的时刻");
    expect(route).not.toContain("不需要今天一次解决");
  });

  it("does not force a fixed assessment or automatic action into this path", () => {
    expect(route).not.toContain("最小3题");
    expect(route).not.toContain("今天可以试的一小步");
    expect(route).not.toContain("自动创建行动");
    expect(route).not.toContain("服务推荐");
  });
});
