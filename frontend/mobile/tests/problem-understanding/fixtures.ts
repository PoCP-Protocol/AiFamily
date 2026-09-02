import type {
  UnderstandingDraft,
  UnderstandingInput,
} from "../../features/problem-understanding/model";

export const concernInput: UnderstandingInput = {
  inputRef: "input-test-001",
  kind: "CONCERN",
  text: "最近一到写作业，我们就容易吵起来。",
  createdAt: "2026-09-01T09:00:00+08:00",
};

export const initialUnderstanding: UnderstandingDraft = {
  runId: "run-test-001",
  signalRef: "signal-test-001",
  signalVersion: 1,
  scopeRef: "family://tenant-test/family-test/problem-understanding",
  reviewedDraftRef: "draft-test-001",
  draftVersion: 3,
  provenanceRef: "source-test-001",
  humanGateReceiptRef: "review-test-001",
  summary: "你在意的不只是作业是否完成，也希望彼此说话时少一些对抗。",
  centralTension: "一边担心孩子落下进度，一边又不希望每晚都靠催促维持秩序。",
  careIntent: "你想守住孩子的学习责任，也想守住彼此能够好好说话的关系。",
  explicitClaims: ["一到写作业就容易争吵"],
  hypotheses: [
    {
      key: "H1",
      statement: "疲惫可能让双方更难听见彼此",
      rationale: "冲突发生在一天接近结束的时候，双方可用的耐心都可能更少。",
      evidenceObservations: ["一到写作业就容易争吵"],
      knowledgeBasisCount: 1,
      confidence: "MEDIUM",
      disconfirmingEvidenceNeeded: "需要了解精力充足时是否也会发生同样的争吵。",
    },
  ],
  familyStrengths: ["你愿意先停下来寻找新的沟通方式"],
  desiredChange: "能讨论作业安排，也能保留彼此的尊重",
  desiredChangeBasis: "EXPLICIT",
  observableSigns: ["开始写作业前能先商量安排", "出现分歧时双方能把话说完"],
  unknowns: [
    { key: "timing", label: "争吵通常从哪个时刻开始" },
    { key: "child-view", label: "孩子怎样理解这些争吵" },
  ],
  followUpQuestions: ["最近一次没有争吵地完成作业时，当时有什么不同？"],
  limitations: ["目前主要根据家长的描述整理，还没有听到孩子怎样理解这件事。"],
  sourceSummary: "根据你写下的内容整理",
  generatedAt: "2026-09-01T09:01:00+08:00",
  mediaCount: 0,
  lifecycle: "PROPOSED",
};
