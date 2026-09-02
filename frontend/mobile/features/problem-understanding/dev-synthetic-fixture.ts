import type {
  ConfirmationBinding,
  UnderstandingDraft,
  UnderstandingInput,
  UnderstandingReceipt,
} from "./model";

export const DEV_SYNTHETIC_PROBLEM_UNDERSTANDING = {
  environment: "DEV_ONLY",
  dataSource: "SYNTHETIC",
  fixtureOnly: true,
  scenarioRef: "problem-understanding-writing-routine-v1",
} as const;

export function createSyntheticConcern(text: string): UnderstandingInput {
  return {
    inputRef: `dev-input-${Date.now()}`,
    kind: "CONCERN",
    text,
    createdAt: new Date().toISOString(),
  };
}

export function createSyntheticUnderstanding(
  correction?: string,
): UnderstandingDraft {
  const draftVersion = correction ? 2 : 1;
  return {
    runId: `dev-run-${draftVersion}`,
    signalRef: "dev-signal-family-conversation",
    signalVersion: draftVersion,
    scopeRef: "family://dev-tenant/dev-family/problem-understanding",
    reviewedDraftRef: `dev-reviewed-draft-${draftVersion}`,
    draftVersion,
    provenanceRef: `dev-synthetic-source-${draftVersion}`,
    humanGateReceiptRef: `dev-review-receipt-${draftVersion}`,
    summary: correction
      ? `你补充说“${correction}”。现在更需要先看见的，是怎样让彼此愿意听完再回应。`
      : "你在意的不只是事情有没有完成，也希望彼此说话时少一些对抗。",
    centralTension: "你既担心事情被耽误，也担心持续催促正在消耗彼此的关系。",
    careIntent: "你真正想守护的是责任感和亲密感能够同时存在。",
    explicitClaims: correction
      ? [correction]
      : ["谈到安排时，家里容易发生争执"],
    hypotheses: [
      {
        key: "H1",
        statement: "疲惫或节奏不一致，可能让双方更难听见彼此",
        rationale: "分歧发生时，双方都可能正承受时间和完成任务的压力。",
        evidenceObservations: correction
          ? [correction]
          : ["谈到安排时，家里容易发生争执"],
        knowledgeBasisCount: 1,
        confidence: "MEDIUM",
        disconfirmingEvidenceNeeded:
          "需要了解时间宽松、双方精力较好时是否仍会出现同样的分歧。",
      },
    ],
    familyStrengths: ["你愿意先停下来，寻找一种更能听见彼此的方式"],
    desiredChange: "能把各自的想法说完整，再一起商量接下来的安排",
    desiredChangeBasis: "INFERRED",
    observableSigns: ["讨论时能轮流把话说完", "安排由双方共同确认"],
    unknowns: [
      { key: "starting-point", label: "分歧通常从哪个时刻开始" },
      { key: "other-view", label: "另一位家人怎样理解当时的情况" },
    ],
    followUpQuestions: ["最近一次商量得比较顺利时，当时发生了什么？"],
    limitations: ["这是开发环境的合成草案，不代表任何真实家庭事实。"],
    sourceSummary: "仅用于开发测试的合成内容",
    generatedAt: "2026-09-01T09:00:00+08:00",
    mediaCount: 0,
    lifecycle: "PROPOSED",
  };
}

export function createSyntheticReceipt(
  binding: ConfirmationBinding,
): UnderstandingReceipt {
  return {
    ...binding,
    receiptRef: `dev-confirmation-${binding.draftVersion}`,
    growthIntentRef: `dev-growth-intent-${binding.draftVersion}`,
  };
}
