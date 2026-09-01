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
  signalRef: "signal-test-001",
  signalVersion: 1,
  scopeRef: "family://tenant-test/family-test/problem-understanding",
  reviewedDraftRef: "draft-test-001",
  draftVersion: 3,
  provenanceRef: "source-test-001",
  humanGateReceiptRef: null,
  summary: "你在意的不只是作业是否完成，也希望彼此说话时少一些对抗。",
  explicitClaims: ["一到写作业就容易争吵"],
  alternativeExplanations: ["疲惫可能让双方更难听见彼此"],
  familyStrengths: ["你愿意先停下来寻找新的沟通方式"],
  desiredChange: "能讨论作业安排，也能保留彼此的尊重",
  unknowns: [
    { key: "timing", label: "争吵通常从哪个时刻开始" },
    { key: "child-view", label: "孩子怎样理解这些争吵" },
  ],
  lifecycle: "PROPOSED",
};
