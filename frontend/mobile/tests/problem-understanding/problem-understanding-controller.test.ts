import { describe, expect, it } from "vitest";

import {
  answerFollowUpQuestion,
  applyConfirmationReceipt,
  beginConfirmation,
  beginCorrection,
  buildUnderstandingMap,
  createProblemUnderstandingState,
  markUnderstandingUnavailable,
  receiveUnderstanding,
  restoreProblemUnderstandingState,
  resumeSavedProblemUnderstanding,
  retryUnderstanding,
  saveProblemUnderstandingForLater,
  serializeProblemUnderstandingState,
  skipClarification,
  submitConcern,
  submitCorrection,
} from "../../features/problem-understanding/controller";
import { concernInput, initialUnderstanding } from "./fixtures";

describe("Problem Understanding mobile controller", () => {
  it("starts with a low-friction concern and exposes unknowns without inventing answers", () => {
    const submitted = submitConcern(
      createProblemUnderstandingState(),
      concernInput,
    );
    const ready = receiveUnderstanding(submitted, initialUnderstanding);
    const map = buildUnderstandingMap(ready);

    expect(ready.phase).toBe("AWAITING_CONFIRMATION");
    expect(map?.originalWords).toEqual([concernInput.text]);
    expect(map?.unknowns).toEqual(initialUnderstanding.unknowns);
    expect(map?.currentUnderstanding).toBe(initialUnderstanding.summary);
  });

  it("keeps the old understanding when a parent corrects it", () => {
    const ready = receiveUnderstanding(
      submitConcern(createProblemUnderstandingState(), concernInput),
      initialUnderstanding,
    );
    const correcting = beginCorrection(ready);
    const corrected = submitCorrection(correcting, {
      inputRef: "input-test-002",
      kind: "CORRECTION",
      text: "真正让我担心的是我们越来越不愿意听对方说话。",
      createdAt: "2026-09-01T09:05:00+08:00",
    });

    expect(corrected.phase).toBe("UNDERSTANDING");
    expect(corrected.drafts).toHaveLength(1);
    expect(corrected.drafts[0]).toMatchObject({
      signalRef: initialUnderstanding.signalRef,
      signalVersion: initialUnderstanding.signalVersion,
      lifecycle: "SUPERSEDED",
      summary: initialUnderstanding.summary,
    });
    expect(corrected.inputs).toHaveLength(2);
    expect(corrected.activeSignal).toBeNull();
  });

  it("turns a generated follow-up question into the next parent reply", () => {
    const ready = receiveUnderstanding(
      submitConcern(createProblemUnderstandingState(), concernInput),
      initialUnderstanding,
    );
    const answering = answerFollowUpQuestion(
      ready,
      initialUnderstanding.followUpQuestions[0],
    );

    expect(answering.phase).toBe("CORRECTING");
    expect(answering.correctionDraft).toContain(
      initialUnderstanding.followUpQuestions[0],
    );
    expect(answering.activeSignal).toEqual(ready.activeSignal);
    expect(answering.drafts).toEqual(ready.drafts);
  });

  it("binds confirmation to the exact signal and version the parent reviewed", () => {
    const ready = receiveUnderstanding(
      submitConcern(createProblemUnderstandingState(), concernInput),
      initialUnderstanding,
    );
    const confirming = beginConfirmation(ready);
    const confirmed = applyConfirmationReceipt(confirming, {
      ...confirming.pendingConfirmation!,
      receiptRef: "receipt-test-001",
      growthIntentRef: "intent-test-001",
    });

    expect(confirming.pendingConfirmation).toEqual({
      signalRef: initialUnderstanding.signalRef,
      signalVersion: initialUnderstanding.signalVersion,
      scopeRef: initialUnderstanding.scopeRef,
      reviewedDraftRef: initialUnderstanding.reviewedDraftRef,
      draftVersion: initialUnderstanding.draftVersion,
      provenanceRef: initialUnderstanding.provenanceRef,
      humanGateReceiptRef: initialUnderstanding.humanGateReceiptRef,
    });
    expect(confirmed.phase).toBe("CONFIRMED");
    expect(confirmed.receipt?.growthIntentRef).toBe("intent-test-001");
    expect(confirmed.drafts[0]?.lifecycle).toBe("CONFIRMED");
  });

  it("rejects a receipt for a different version and asks the parent to review again", () => {
    const ready = receiveUnderstanding(
      submitConcern(createProblemUnderstandingState(), concernInput),
      initialUnderstanding,
    );
    const confirming = beginConfirmation(ready);
    const result = applyConfirmationReceipt(confirming, {
      ...confirming.pendingConfirmation!,
      receiptRef: "receipt-test-stale",
      growthIntentRef: "intent-test-stale",
      signalVersion: initialUnderstanding.signalVersion + 1,
    });

    expect(result.phase).toBe("AWAITING_CONFIRMATION");
    expect(result.receipt).toBeNull();
    expect(result.recoveryMessage).toContain("最新理解");
  });

  it.each([
    ["scopeRef", "family://tenant-test/another-family/problem-understanding"],
    ["reviewedDraftRef", "draft-test-other"],
    ["draftVersion", initialUnderstanding.draftVersion + 1],
    ["provenanceRef", "source-test-other"],
    ["humanGateReceiptRef", "review-test-other"],
  ] as const)(
    "fails closed when %s does not match the reviewed draft",
    (field, value) => {
      const ready = receiveUnderstanding(
        submitConcern(createProblemUnderstandingState(), concernInput),
        initialUnderstanding,
      );
      const confirming = beginConfirmation(ready);
      const result = applyConfirmationReceipt(confirming, {
        ...confirming.pendingConfirmation!,
        [field]: value,
        receiptRef: "receipt-test-mismatch",
        growthIntentRef: "intent-test-mismatch",
      });

      expect(result.phase).toBe("AWAITING_CONFIRMATION");
      expect(result.receipt).toBeNull();
      expect(result.recoveryMessage).toContain("最新理解");
    },
  );

  it("preserves all entered content when understanding is unavailable and can retry", () => {
    const submitted = submitConcern(
      createProblemUnderstandingState(),
      concernInput,
    );
    const unavailable = markUnderstandingUnavailable(submitted);
    const retrying = retryUnderstanding(unavailable);

    expect(unavailable.phase).toBe("AI_UNAVAILABLE");
    expect(unavailable.inputs).toEqual(submitted.inputs);
    expect(unavailable.recoveryMessage).toContain("已经保留");
    expect(retrying.phase).toBe("UNDERSTANDING");
    expect(retrying.inputs).toEqual(submitted.inputs);
    expect(retrying.recoveryMessage).toBeNull();
  });

  it("lets the adult skip clarification without inventing missing evidence", () => {
    const ready = receiveUnderstanding(
      submitConcern(createProblemUnderstandingState(), concernInput),
      initialUnderstanding,
    );
    const skipped = skipClarification(ready);
    const map = buildUnderstandingMap(skipped);

    expect(skipped.phase).toBe("AWAITING_CONFIRMATION");
    expect(map?.clarificationSkipped).toBe(true);
    expect(map?.unknowns).toEqual(initialUnderstanding.unknowns);
    expect(map?.canConfirm).toBe(true);
  });

  it("saves an exit and restores the exact unconfirmed conversation", () => {
    const ready = receiveUnderstanding(
      submitConcern(createProblemUnderstandingState(), concernInput),
      initialUnderstanding,
    );
    const saved = saveProblemUnderstandingForLater(
      ready,
      "2026-09-01T10:00:00+08:00",
    );
    const restored = restoreProblemUnderstandingState(
      serializeProblemUnderstandingState(saved),
    );
    const resumed = resumeSavedProblemUnderstanding(restored);

    expect(restored.phase).toBe("SAVED");
    expect(restored.inputs).toEqual([concernInput]);
    expect(restored.drafts).toEqual([{ ...initialUnderstanding }]);
    expect(resumed.phase).toBe("AWAITING_CONFIRMATION");
    expect(buildUnderstandingMap(resumed)?.currentUnderstanding).toBe(
      initialUnderstanding.summary,
    );
  });

  it("fails closed with a recoverable message when saved content is damaged", () => {
    const restored = restoreProblemUnderstandingState("{not-json");

    expect(restored.phase).toBe("ERROR");
    expect(restored.inputs).toEqual([]);
    expect(restored.recoveryMessage).toContain("重新说一遍");
  });
});
