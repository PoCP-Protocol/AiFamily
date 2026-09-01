import type {
  ConfirmationBinding,
  DraftBinding,
  ProblemUnderstandingState,
  UnderstandingDraft,
  UnderstandingInput,
  UnderstandingMapViewModel,
  UnderstandingReceipt,
  ViewedDraftBinding,
} from "./model";

export const PROBLEM_UNDERSTANDING_COPY = {
  heading: "说说家里最近发生的一件事",
  prompt: "不用一次说完整，我们可以一起慢慢理清。",
  unknownHeading: "还不确定",
  correctionHeading: "哪里需要换一种说法？",
  confirmAction: "对，就是这样",
  unavailable: "这次理解暂时没有完成。你说过的内容已经保留，可以稍后继续。",
} as const;

const PERSISTENCE_VERSION = 1;

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
    clarificationSkipped: false,
    savedAt: null,
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
      viewEventRef: null,
    },
    pendingConfirmation: null,
    recoveryMessage: null,
    clarificationSkipped: false,
  };
}

export function beginCorrection(
  state: ProblemUnderstandingState,
): ProblemUnderstandingState {
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
    clarificationSkipped: false,
  };
}

export function beginConfirmation(
  state: ProblemUnderstandingState,
): ProblemUnderstandingState {
  if (
    !state.activeSignal ||
    !state.activeSignal.viewEventRef ||
    state.phase !== "AWAITING_CONFIRMATION"
  ) {
    return { ...state, phase: "ERROR" };
  }

  return {
    ...state,
    phase: "CONFIRMING",
    pendingConfirmation: {
      signalRef: state.activeSignal.signalRef,
      signalVersion: state.activeSignal.signalVersion,
      scopeRef: state.activeSignal.scopeRef,
      reviewedDraftRef: state.activeSignal.reviewedDraftRef,
      draftVersion: state.activeSignal.draftVersion,
      provenanceRef: state.activeSignal.provenanceRef,
      viewEventRef: state.activeSignal.viewEventRef,
    },
  };
}

export function applyUnderstandingView(
  state: ProblemUnderstandingState,
  viewed: ViewedDraftBinding,
): ProblemUnderstandingState {
  if (!sameDraftBinding(state.activeSignal, viewed)) {
    return {
      ...state,
      recoveryMessage: "内容已经更新，请看过最新理解后再确认。",
    };
  }
  const activeSignal = state.activeSignal;
  if (activeSignal === null) return state;
  return {
    ...state,
    activeSignal: { ...activeSignal, viewEventRef: viewed.viewEventRef },
    recoveryMessage: null,
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
    savedAt: null,
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

export function skipClarification(
  state: ProblemUnderstandingState,
): ProblemUnderstandingState {
  if (state.phase !== "AWAITING_CONFIRMATION" || !state.activeSignal) {
    return { ...state, phase: "ERROR" };
  }
  return { ...state, clarificationSkipped: true, recoveryMessage: null };
}

export function saveProblemUnderstandingForLater(
  state: ProblemUnderstandingState,
  savedAt: string,
): ProblemUnderstandingState {
  if (state.inputs.length === 0) return state;
  return {
    ...state,
    phase: "SAVED",
    pendingConfirmation: null,
    savedAt,
  };
}

export function resumeSavedProblemUnderstanding(
  state: ProblemUnderstandingState,
): ProblemUnderstandingState {
  if (state.phase !== "SAVED") return state;
  return {
    ...state,
    phase: state.activeSignal ? "AWAITING_CONFIRMATION" : "DRAFTING",
    savedAt: null,
  };
}

export function serializeProblemUnderstandingState(
  state: ProblemUnderstandingState,
): string {
  return JSON.stringify({ version: PERSISTENCE_VERSION, state });
}

export function restoreProblemUnderstandingState(
  serialized: string | null,
): ProblemUnderstandingState {
  if (!serialized) return createProblemUnderstandingState();
  try {
    const envelope = JSON.parse(serialized) as {
      version?: number;
      state?: Partial<ProblemUnderstandingState>;
    };
    const state = envelope.state;
    if (
      envelope.version !== PERSISTENCE_VERSION ||
      !state ||
      !Array.isArray(state.inputs) ||
      !Array.isArray(state.drafts)
    ) {
      return createProblemUnderstandingState();
    }
    return {
      ...createProblemUnderstandingState(),
      ...state,
      concernDraft:
        typeof state.concernDraft === "string" ? state.concernDraft : "",
      correctionDraft:
        typeof state.correctionDraft === "string" ? state.correctionDraft : "",
      clarificationSkipped: state.clarificationSkipped === true,
      savedAt: typeof state.savedAt === "string" ? state.savedAt : null,
    } as ProblemUnderstandingState;
  } catch {
    return {
      ...createProblemUnderstandingState(),
      phase: "ERROR",
      recoveryMessage:
        "没有找回上次保存的内容。你可以重新说一遍，我们会从这里继续。",
    };
  }
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
      draft.lifecycle === "PROPOSED" &&
      state.phase === "AWAITING_CONFIRMATION",
    clarificationSkipped: state.clarificationSkipped,
  };
}

function sameBinding(
  expected: ViewedDraftBinding | null,
  actual: UnderstandingReceipt,
): boolean {
  return (
    expected !== null &&
    expected.signalRef === actual.signalRef &&
    expected.signalVersion === actual.signalVersion &&
    expected.scopeRef === actual.scopeRef &&
    expected.reviewedDraftRef === actual.reviewedDraftRef &&
    expected.draftVersion === actual.draftVersion &&
    expected.provenanceRef === actual.provenanceRef &&
    expected.viewEventRef === actual.viewEventRef &&
    actual.humanGateReceiptRef === actual.receiptRef
  );
}


function sameDraftBinding(
  expected: DraftBinding | null,
  actual: ViewedDraftBinding,
): boolean {
  return (
    expected !== null &&
    expected.signalRef === actual.signalRef &&
    expected.signalVersion === actual.signalVersion &&
    expected.scopeRef === actual.scopeRef &&
    expected.reviewedDraftRef === actual.reviewedDraftRef &&
    expected.draftVersion === actual.draftVersion &&
    expected.provenanceRef === actual.provenanceRef
  );
}
