import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  createSyntheticReceipt,
  createSyntheticUnderstanding,
  DEV_SYNTHETIC_PROBLEM_UNDERSTANDING,
} from "../../features/problem-understanding/dev-synthetic-fixture";

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
    expect(route).toContain("useColors");
    expect(rootLayout).toContain("<ResponsivePlatformShell>");
  });

  it("keeps synthetic data explicitly limited to development", () => {
    expect(DEV_SYNTHETIC_PROBLEM_UNDERSTANDING).toEqual({
      environment: "DEV_ONLY",
      dataSource: "SYNTHETIC",
      fixtureOnly: true,
      scenarioRef: "problem-understanding-writing-routine-v1",
    });
    expect(route).toContain("__DEV__");
    expect(route).toContain('environment === "DEV_ONLY"');
    expect(route).toContain("fixtureOnly");
  });

  it("creates a receipt with the complete reviewed-draft binding", () => {
    const draft = createSyntheticUnderstanding();
    const receipt = createSyntheticReceipt({
      signalRef: draft.signalRef,
      signalVersion: draft.signalVersion,
      scopeRef: draft.scopeRef,
      reviewedDraftRef: draft.reviewedDraftRef,
      draftVersion: draft.draftVersion,
      provenanceRef: draft.provenanceRef,
      humanGateReceiptRef: draft.humanGateReceiptRef,
    });

    expect(receipt).toMatchObject({
      scopeRef: draft.scopeRef,
      reviewedDraftRef: draft.reviewedDraftRef,
      draftVersion: draft.draftVersion,
      provenanceRef: draft.provenanceRef,
      humanGateReceiptRef: draft.humanGateReceiptRef,
    });
  });

  it("does not expose internal implementation language in visible copy", () => {
    expect(route).not.toMatch(
      />\s*(DEV|SYNTHETIC|DTO|GrowthCase|provenance)\s*</,
    );
    expect(route).not.toContain("overall_score");
    expect(route).not.toContain("peer_reference");
    expect(route).not.toContain("默认50");
  });

  it("offers a complete human-readable confirm, exit, delete, and restore path", () => {
    expect(route).toContain("AsyncStorage.getItem");
    expect(route).toContain("AsyncStorage.setItem");
    expect(route).toContain("AsyncStorage.removeItem");
    expect(route).toContain("继续这次对话");
    expect(route).toContain("删除已保存内容");
    expect(route).toContain("正在找回你上次保存的内容");
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
    expect(components).toContain("点“继续”后，我们才会整理这段话");
  });

  it("does not force a fixed assessment or automatic action into this path", () => {
    expect(route).not.toContain("最小3题");
    expect(route).not.toContain("今天可以试的一小步");
    expect(route).not.toContain("自动创建行动");
    expect(route).not.toContain("服务推荐");
  });
});
