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
  humanGateReceiptRef: string;
  summary: string;
  explicitClaims: readonly string[];
  alternativeExplanations: readonly string[];
  familyStrengths: readonly string[];
  desiredChange: string;
  unknowns: readonly UnderstandingUnknown[];
  lifecycle: "PROPOSED" | "SUPERSEDED" | "CONFIRMED";
}

export interface ConfirmationBinding {
  signalRef: string;
  signalVersion: number;
  scopeRef: string;
  reviewedDraftRef: string;
  draftVersion: number;
  provenanceRef: string;
  humanGateReceiptRef: string;
}

export interface UnderstandingReceipt extends ConfirmationBinding {
  receiptRef: string;
  growthIntentRef: string;
}

export interface ProblemUnderstandingState {
  phase: ProblemUnderstandingPhase;
  concernDraft: string;
  correctionDraft: string;
  inputs: readonly UnderstandingInput[];
  drafts: readonly UnderstandingDraft[];
  activeSignal: ConfirmationBinding | null;
  pendingConfirmation: ConfirmationBinding | null;
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
