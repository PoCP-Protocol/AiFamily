import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

type LoopDFixture = {
  sceneId: string;
  fixtureId: string;
  environment: "DEV_ONLY";
  dataSource: "SYNTHETIC";
  fixtureOnly: true;
  scope: { tenantId: string; familyId: string; guardianId: string };
  entry: { route: string; label: string };
  inputs: Array<{
    ref: string;
    modality: "TEXT" | "IMAGE_OCR" | "VOICE_TRANSCRIPT";
    displayLabel: string;
    content: string;
    source: "SYNTHETIC";
    guardianConfirmed: true;
  }>;
  understandingDraft: {
    status: "DRAFT";
    title: string;
    currentUnderstanding: string;
    sourceRefs: string[];
    sourceLabels: string[];
    unknowns: string[];
    editableFields: string[];
    requiresGuardianReview: true;
    mayMutateBusinessState: false;
    knowledge: {
      status: "NOT_CONNECTED";
      displayMessage: string;
      references: [];
    };
  };
  guardianReview: {
    decision: "EDIT";
    editedUnderstanding: string;
    reason: string;
  };
  savedView: {
    route: string;
    sectionLabel: string;
    state: "PRIVATE_DRAFT";
    visibility: "FAMILY_PRIVATE";
    reloadExpected: true;
    externalEffect: false;
  };
};

const fixturePath = resolve(
  __dirname,
  "../dev-fixtures/loop-d-private-note-v1.json",
);
const fixture = JSON.parse(readFileSync(fixturePath, "utf8")) as LoopDFixture;

describe("LOOP-D-PRIVATE-NOTE consumer fixture", () => {
  it("combines confirmed text, image OCR, and voice transcript into an editable draft", () => {
    expect(fixture.sceneId).toBe("LOOP-D-PRIVATE-NOTE");
    expect(fixture.environment).toBe("DEV_ONLY");
    expect(fixture.dataSource).toBe("SYNTHETIC");
    expect(fixture.fixtureOnly).toBe(true);
    expect(fixture.inputs.map((input) => input.modality)).toEqual([
      "TEXT",
      "IMAGE_OCR",
      "VOICE_TRANSCRIPT",
    ]);
    expect(fixture.inputs.every((input) => input.guardianConfirmed)).toBe(true);
    expect(fixture.understandingDraft.sourceRefs).toEqual(
      fixture.inputs.map((input) => input.ref),
    );
    expect(fixture.understandingDraft.unknowns.length).toBeGreaterThan(0);
    expect(fixture.understandingDraft.editableFields).toEqual([
      "title",
      "currentUnderstanding",
    ]);
  });

  it("fails closed when canonical reviewed knowledge is unavailable", () => {
    expect(fixture.understandingDraft.knowledge).toMatchObject({
      status: "NOT_CONNECTED",
      references: [],
    });
    expect(fixture.understandingDraft.knowledge.displayMessage).toContain(
      "尚未连接经过审核的参考内容",
    );
    expect(fixture.understandingDraft.mayMutateBusinessState).toBe(false);
  });

  it("replays the guardian edit into a family-private saved view", () => {
    const isolatedStore = new Map<string, string>();
    const storageKey = `${fixture.scope.tenantId}:${fixture.scope.familyId}:${fixture.fixtureId}`;
    isolatedStore.set(
      storageKey,
      JSON.stringify({
        understanding: fixture.guardianReview.editedUnderstanding,
        savedView: fixture.savedView,
      }),
    );

    const afterRestart = JSON.parse(
      isolatedStore.get(storageKey) ?? "null",
    ) as {
      understanding: string;
      savedView: LoopDFixture["savedView"];
    };
    expect(afterRestart.understanding).toBe(
      "我们先观察开始步骤和疲惫程度，不急着判断原因。",
    );
    expect(afterRestart.savedView).toMatchObject({
      route: "/ui/UI-28",
      sectionLabel: "我的家庭知识",
      state: "PRIVATE_DRAFT",
      visibility: "FAMILY_PRIVATE",
      reloadExpected: true,
      externalEffect: false,
    });
  });

  it("keeps engineering vocabulary out of visible copy", () => {
    const visibleCopy = [
      fixture.entry.label,
      ...fixture.inputs.map((input) => input.displayLabel),
      fixture.understandingDraft.title,
      fixture.understandingDraft.currentUnderstanding,
      fixture.understandingDraft.knowledge.displayMessage,
      fixture.savedView.sectionLabel,
    ].join("\n");
    expect(visibleCopy).not.toMatch(
      /fixture|provider|provenance|fail.closed|DEV_ONLY|SYNTHETIC|NOT_CONNECTED/i,
    );
  });

  it.fails("remains red until UI-26 consumes this exact scene fixture", () => {
    const ui26 = readFileSync(
      resolve(__dirname, "../app/ui/UI-26.tsx"),
      "utf8",
    );
    expect(ui26).toContain(fixture.fixtureId);
    expect(ui26).toContain(fixture.savedView.sectionLabel);
  });
});
