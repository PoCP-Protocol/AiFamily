export type ProblemUnderstandingPhase =
  | "DRAFTING"
  | "UNDERSTANDING"
  | "AWAITING_CONFIRMATION"
  | "CORRECTING"
  | "CONFIRMING"
  | "CONFIRMED"
  | "SAVED"
  | "AI_UNAVAILABLE"
  | "ERROR";

export type UnderstandingInputKind = "CONCERN" | "CORRECTION" | "FOLLOW_UP";

export interface UnderstandingInput {
  inputRef: string;
  kind: UnderstandingInputKind;
  text: string;
  createdAt: string;
}

export interface UnderstandingUnknown {
  key: string;
  label: string;
}

export interface UnderstandingDraft {
  signalRef: string;
  signalVersion: number;
  scopeRef: string;
  reviewedDraftRef: string;
  draftVersion: number;
  provenanceRef: string;
  humanGateReceiptRef: string | null;
  summary: string;
  explicitClaims: readonly string[];
  alternativeExplanations: readonly string[];
  familyStrengths: readonly string[];
  desiredChange: string;
  unknowns: readonly UnderstandingUnknown[];
  lifecycle: "PROPOSED" | "SUPERSEDED" | "CONFIRMED";
}

export interface DraftBinding {
  signalRef: string;
  signalVersion: number;
  scopeRef: string;
  reviewedDraftRef: string;
  draftVersion: number;
  provenanceRef: string;
  humanGateReceiptRef: string | null;
  viewEventRef: string | null;
}

export interface ViewedDraftBinding {
  signalRef: string;
  signalVersion: number;
  scopeRef: string;
  reviewedDraftRef: string;
  draftVersion: number;
  provenanceRef: string;
  viewEventRef: string;
}

export interface ConfirmationBinding extends ViewedDraftBinding {
  humanGateReceiptRef: string;
}

export interface UnderstandingReceipt extends ConfirmationBinding {
  receiptRef: string;
  growthIntentRef: string | null;
}

export interface ProblemUnderstandingState {
  phase: ProblemUnderstandingPhase;
  concernDraft: string;
  correctionDraft: string;
  inputs: readonly UnderstandingInput[];
  drafts: readonly UnderstandingDraft[];
  activeSignal: DraftBinding | null;
  pendingConfirmation: ViewedDraftBinding | null;
  receipt: UnderstandingReceipt | null;
  recoveryMessage: string | null;
  clarificationSkipped: boolean;
  savedAt: string | null;
}

export interface UnderstandingMapViewModel {
  originalWords: readonly string[];
  currentUnderstanding: string;
  alternativeExplanations: readonly string[];
  familyStrengths: readonly string[];
  desiredChange: string;
  unknowns: readonly UnderstandingUnknown[];
  canCorrect: boolean;
  canConfirm: boolean;
  clarificationSkipped: boolean;
}
