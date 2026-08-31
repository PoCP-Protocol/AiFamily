import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  createSyntheticReceipt,
  createSyntheticUnderstanding,
  DEV_SYNTHETIC_PROBLEM_UNDERSTANDING,
} from "../../features/problem-understanding/dev-synthetic-fixture";

const route = readFileSync(
  resolve(process.cwd(), "app/family/problem-understanding.tsx"),
  "utf8",
);
const rootLayout = readFileSync(resolve(process.cwd(), "app/_layout.tsx"), "utf8");

describe("Problem Understanding standalone Expo route", () => {
  it("composes the reusable experience inside the established platform shell", () => {
    expect(route).toContain("ConcernComposer");
    expect(route).toContain("UnderstandingMap");
    expect(route).toContain("CorrectionConfirmation");
    expect(route).toContain("RecoveryNotice");
    expect(route).toContain("useColors");
    expect(rootLayout).toContain("<ResponsivePlatformShell>");
  });

  it("keeps synthetic data explicitly limited to development", () => {
    expect(DEV_SYNTHETIC_PROBLEM_UNDERSTANDING).toEqual({
      environment: "DEV",
      dataSource: "SYNTHETIC",
      scenarioRef: "problem-understanding-writing-routine-v1",
    });
    expect(route).toContain("__DEV__");
    expect(route).toContain('dataSource === "SYNTHETIC"');
  });

  it("creates a receipt with the complete reviewed-draft binding", () => {
    const draft = createSyntheticUnderstanding();
    const receipt = createSyntheticReceipt({
      signalRef: draft.signalRef,
      signalVersion: draft.signalVersion,
      scopeRef: draft.scopeRef,
      reviewedDraftRef: draft.reviewedDraftRef,
      draftVersion: draft.draftVersion,
      provenanceRef: draft.provenanceRef,
      humanGateReceiptRef: draft.humanGateReceiptRef,
    });

    expect(receipt).toMatchObject({
      scopeRef: draft.scopeRef,
      reviewedDraftRef: draft.reviewedDraftRef,
      draftVersion: draft.draftVersion,
      provenanceRef: draft.provenanceRef,
      humanGateReceiptRef: draft.humanGateReceiptRef,
    });
  });

  it("does not expose internal implementation language in visible copy", () => {
    expect(route).not.toMatch(/>\s*(DEV|SYNTHETIC|DTO|GrowthCase|provenance)\s*</);
    expect(route).not.toContain("overall_score");
    expect(route).not.toContain("peer_reference");
    expect(route).not.toContain("默认50");
  });
});
