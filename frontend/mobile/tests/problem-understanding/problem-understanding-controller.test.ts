import { describe, expect, it } from "vitest";

import {
  applyConfirmationReceipt,
  beginConfirmation,
  beginCorrection,
  buildUnderstandingMap,
  createProblemUnderstandingState,
  markUnderstandingUnavailable,
  receiveUnderstanding,
  retryUnderstanding,
  submitConcern,
  submitCorrection,
} from "../../features/problem-understanding/controller";
import { concernInput, initialUnderstanding } from "./fixtures";

describe("Problem Understanding mobile controller", () => {
  it("starts with a low-friction concern and exposes unknowns without inventing answers", () => {
    const submitted = submitConcern(createProblemUnderstandingState(), concernInput);
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

  it("binds confirmation to the exact signal and version the parent reviewed", () => {
    const ready = receiveUnderstanding(
      submitConcern(createProblemUnderstandingState(), concernInput),
      initialUnderstanding,
    );
    const confirming = beginConfirmation(ready);
    const confirmed = applyConfirmationReceipt(confirming, {
      receiptRef: "receipt-test-001",
      growthIntentRef: "intent-test-001",
      signalRef: initialUnderstanding.signalRef,
      signalVersion: initialUnderstanding.signalVersion,
    });

    expect(confirming.pendingConfirmation).toEqual({
      signalRef: initialUnderstanding.signalRef,
      signalVersion: initialUnderstanding.signalVersion,
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
    const result = applyConfirmationReceipt(beginConfirmation(ready), {
      receiptRef: "receipt-test-stale",
      growthIntentRef: "intent-test-stale",
      signalRef: initialUnderstanding.signalRef,
      signalVersion: initialUnderstanding.signalVersion + 1,
    });

    expect(result.phase).toBe("AWAITING_CONFIRMATION");
    expect(result.receipt).toBeNull();
    expect(result.recoveryMessage).toContain("最新理解");
  });

  it("preserves all entered content when understanding is unavailable and can retry", () => {
    const submitted = submitConcern(createProblemUnderstandingState(), concernInput);
    const unavailable = markUnderstandingUnavailable(submitted);
    const retrying = retryUnderstanding(unavailable);

    expect(unavailable.phase).toBe("AI_UNAVAILABLE");
    expect(unavailable.inputs).toEqual(submitted.inputs);
    expect(unavailable.recoveryMessage).toContain("已经保留");
    expect(retrying.phase).toBe("UNDERSTANDING");
    expect(retrying.inputs).toEqual(submitted.inputs);
    expect(retrying.recoveryMessage).toBeNull();
  });
});
