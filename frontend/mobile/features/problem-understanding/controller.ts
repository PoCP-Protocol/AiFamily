import type {
  ConfirmationBinding,
  ProblemUnderstandingState,
  UnderstandingDraft,
  UnderstandingInput,
  UnderstandingMapViewModel,
  UnderstandingReceipt,
} from "./model";

export const PROBLEM_UNDERSTANDING_COPY = {
  heading: "说说家里最近发生的一件事",
  prompt: "不用一次说完整，我们可以一起慢慢理清。",
  unknownHeading: "我还不确定的",
  correctionHeading: "哪里需要换一种说法？",
  confirmAction: "这就是我现在想先处理的事",
  unavailable: "这次理解暂时没有完成。你说过的内容已经保留，可以稍后继续。",
} as const;

export function createProblemUnderstandingState(): ProblemUnderstandingState {
  return {
    phase: "DRAFTING",
    concernDraft: "",
    correctionDraft: "",
    inputs: [],
    drafts: [],
    activeSignal: null,
    pendingConfirmation: null,
    receipt: null,
    recoveryMessage: null,
  };
}

export function updateConcernDraft(
  state: ProblemUnderstandingState,
  concernDraft: string,
): ProblemUnderstandingState {
  return { ...state, concernDraft };
}

export function submitConcern(
  state: ProblemUnderstandingState,
  input: UnderstandingInput,
): ProblemUnderstandingState {
  if (input.kind !== "CONCERN" || input.text.trim().length === 0) {
    return { ...state, phase: "ERROR" };
  }

  return {
    ...state,
    phase: "UNDERSTANDING",
    concernDraft: "",
    inputs: [...state.inputs, { ...input, text: input.text.trim() }],
    recoveryMessage: null,
  };
}

export function receiveUnderstanding(
  state: ProblemUnderstandingState,
  draft: UnderstandingDraft,
): ProblemUnderstandingState {
  const drafts = state.drafts.map((existing) =>
    existing.lifecycle === "PROPOSED"
      ? { ...existing, lifecycle: "SUPERSEDED" as const }
      : existing,
  );

  return {
    ...state,
    phase: "AWAITING_CONFIRMATION",
    drafts: [...drafts, { ...draft, lifecycle: "PROPOSED" }],
    activeSignal: {
      signalRef: draft.signalRef,
      signalVersion: draft.signalVersion,
      scopeRef: draft.scopeRef,
      reviewedDraftRef: draft.reviewedDraftRef,
      draftVersion: draft.draftVersion,
      provenanceRef: draft.provenanceRef,
      humanGateReceiptRef: draft.humanGateReceiptRef,
    },
    pendingConfirmation: null,
    recoveryMessage: null,
  };
}

export function beginCorrection(state: ProblemUnderstandingState): ProblemUnderstandingState {
  if (!state.activeSignal) {
    return { ...state, phase: "ERROR" };
  }
  return { ...state, phase: "CORRECTING", correctionDraft: "" };
}

export function updateCorrectionDraft(
  state: ProblemUnderstandingState,
  correctionDraft: string,
): ProblemUnderstandingState {
  return { ...state, correctionDraft };
}

export function submitCorrection(
  state: ProblemUnderstandingState,
  correction: UnderstandingInput,
): ProblemUnderstandingState {
  if (correction.kind !== "CORRECTION" || correction.text.trim().length === 0) {
    return { ...state, phase: "ERROR" };
  }

  return {
    ...state,
    phase: "UNDERSTANDING",
    correctionDraft: "",
    inputs: [...state.inputs, { ...correction, text: correction.text.trim() }],
    drafts: state.drafts.map((draft) =>
      draft.lifecycle === "PROPOSED"
        ? { ...draft, lifecycle: "SUPERSEDED" as const }
        : draft,
    ),
    activeSignal: null,
    pendingConfirmation: null,
    recoveryMessage: null,
  };
}

export function beginConfirmation(
  state: ProblemUnderstandingState,
): ProblemUnderstandingState {
  if (!state.activeSignal || state.phase !== "AWAITING_CONFIRMATION") {
    return { ...state, phase: "ERROR" };
  }

  return {
    ...state,
    phase: "CONFIRMING",
    pendingConfirmation: { ...state.activeSignal },
  };
}

export function applyConfirmationReceipt(
  state: ProblemUnderstandingState,
  receipt: UnderstandingReceipt,
): ProblemUnderstandingState {
  if (!sameBinding(state.pendingConfirmation, receipt)) {
    return {
      ...state,
      phase: "AWAITING_CONFIRMATION",
      pendingConfirmation: null,
      recoveryMessage: "内容已经更新，请看过最新理解后再确认。",
    };
  }

  return {
    ...state,
    phase: "CONFIRMED",
    receipt,
    pendingConfirmation: null,
    drafts: state.drafts.map((draft) =>
      draft.signalRef === receipt.signalRef &&
      draft.signalVersion === receipt.signalVersion
        ? { ...draft, lifecycle: "CONFIRMED" as const }
        : draft,
    ),
    recoveryMessage: null,
  };
}

export function markUnderstandingUnavailable(
  state: ProblemUnderstandingState,
): ProblemUnderstandingState {
  return {
    ...state,
    phase: "AI_UNAVAILABLE",
    recoveryMessage: PROBLEM_UNDERSTANDING_COPY.unavailable,
  };
}

export function retryUnderstanding(
  state: ProblemUnderstandingState,
): ProblemUnderstandingState {
  return {
    ...state,
    phase: "UNDERSTANDING",
    recoveryMessage: null,
  };
}

export function selectCurrentDraft(
  state: ProblemUnderstandingState,
): UnderstandingDraft | null {
  if (!state.activeSignal) return null;
  return (
    state.drafts.find(
      (draft) =>
        draft.signalRef === state.activeSignal?.signalRef &&
        draft.signalVersion === state.activeSignal.signalVersion &&
        draft.reviewedDraftRef === state.activeSignal.reviewedDraftRef &&
        draft.draftVersion === state.activeSignal.draftVersion,
    ) ?? null
  );
}

export function buildUnderstandingMap(
  state: ProblemUnderstandingState,
): UnderstandingMapViewModel | null {
  const draft = selectCurrentDraft(state);
  if (!draft) return null;

  return {
    originalWords: state.inputs.map((input) => input.text),
    currentUnderstanding: draft.summary,
    alternativeExplanations: draft.alternativeExplanations,
    familyStrengths: draft.familyStrengths,
    desiredChange: draft.desiredChange,
    unknowns: draft.unknowns,
    canCorrect: draft.lifecycle === "PROPOSED",
    canConfirm:
      draft.lifecycle === "PROPOSED" && state.phase === "AWAITING_CONFIRMATION",
  };
}

function sameBinding(
  expected: ConfirmationBinding | null,
  actual: ConfirmationBinding,
): boolean {
  return (
    expected !== null &&
    expected.signalRef === actual.signalRef &&
    expected.signalVersion === actual.signalVersion &&
    expected.scopeRef === actual.scopeRef &&
    expected.reviewedDraftRef === actual.reviewedDraftRef &&
    expected.draftVersion === actual.draftVersion &&
    expected.provenanceRef === actual.provenanceRef &&
    expected.humanGateReceiptRef === actual.humanGateReceiptRef
  );
}
