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
  runId: string;
  signalRef: string;
  signalVersion: number;
  scopeRef: string;
  reviewedDraftRef: string;
  draftVersion: number;
  provenanceRef: string;
  humanGateReceiptRef: string | null;
  summary: string;
  centralTension: string;
  careIntent: string;
  explicitClaims: readonly string[];
  alternativeExplanations: readonly string[];
  familyStrengths: readonly string[];
  desiredChange: string;
  desiredChangeBasis: "EXPLICIT" | "INFERRED";
  observableSigns: readonly string[];
  unknowns: readonly UnderstandingUnknown[];
  followUpQuestions: readonly string[];
  limitations: readonly string[];
  sourceSummary: string;
  generatedAt: string;
  mediaCount: number;
  lifecycle: "PROPOSED" | "SUPERSEDED" | "CONFIRMED";
}

export interface AuthorizedMediaAttachment {
  mediaType: "IMAGE";
  uri: string;
  mimeType: string;
  sha256: string;
}

export interface DraftBinding {
  signalRef: string;
  signalVersion: number;
  scopeRef: string;
  reviewedDraftRef: string;
  draftVersion: number;
  provenanceRef: string;
  humanGateReceiptRef: string | null;
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
  activeSignal: DraftBinding | null;
  pendingConfirmation: ConfirmationBinding | null;
  receipt: UnderstandingReceipt | null;
  recoveryMessage: string | null;
  clarificationSkipped: boolean;
  savedAt: string | null;
}

export interface UnderstandingMapViewModel {
  originalWords: readonly string[];
  currentUnderstanding: string;
  centralTension: string;
  careIntent: string;
  alternativeExplanations: readonly string[];
  familyStrengths: readonly string[];
  desiredChange: string;
  desiredChangeBasis: "EXPLICIT" | "INFERRED";
  observableSigns: readonly string[];
  unknowns: readonly UnderstandingUnknown[];
  followUpQuestions: readonly string[];
  limitations: readonly string[];
  sourceSummary: string;
  generatedAt: string;
  mediaCount: number;
  draftVersion: number;
  canCorrect: boolean;
  canConfirm: boolean;
  clarificationSkipped: boolean;
}
