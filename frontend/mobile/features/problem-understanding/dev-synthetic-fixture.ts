import type {
  ConfirmationBinding,
  UnderstandingDraft,
  UnderstandingInput,
  UnderstandingReceipt,
} from "./model";

export const DEV_SYNTHETIC_PROBLEM_UNDERSTANDING = {
  environment: "DEV",
  dataSource: "SYNTHETIC",
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
    explicitClaims: correction ? [correction] : ["谈到安排时，家里容易发生争执"],
    alternativeExplanations: ["疲惫或节奏不一致，也可能让双方更难听见彼此"],
    familyStrengths: ["你愿意先停下来，寻找一种更能听见彼此的方式"],
    desiredChange: "能把各自的想法说完整，再一起商量接下来的安排",
    unknowns: [
      { key: "starting-point", label: "分歧通常从哪个时刻开始" },
      { key: "other-view", label: "另一位家人怎样理解当时的情况" },
    ],
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
