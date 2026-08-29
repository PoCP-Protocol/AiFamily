import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const ui05 = readFileSync(resolve(process.cwd(), "app/ui/UI-05.tsx"), "utf8");
const ui09 = readFileSync(resolve(process.cwd(), "app/ui/UI-09.tsx"), "utf8");
const client = readFileSync(resolve(process.cwd(), "lib/family/family-api-client.ts"), "utf8");

describe("UI-05/UI-09 real family session harness contract", () => {
  it("reads the current Journey Plan with the established Family API session before rendering a phase decision", () => {
    expect(ui05).toContain("useFamilyApiSession");
    expect(ui05).toContain("familyApi.getJourneyPlan");
    expect(ui05).toContain('status === "REVIEW_DUE"');
    expect(ui05).toContain("familyApi.reviewJourneyPhase");
    expect(ui05).toContain('`ui05-review-${plan.plan_id}-${decision}`');
  });

  it("checks in the server-provided Journey Plan action before acknowledging the local visual receipt", () => {
    expect(ui09).toContain("familyApi.getFamilyToday");
    expect(ui09).toContain("remoteAction?.journey_plan_id");
    expect(ui09).toContain("familyApi.changeTodayTaskState");
    expect(ui09).toContain('"START"');
    expect(ui09).toContain('"PAUSE"');
    expect(ui09).toContain('"RESUME"');
    expect(ui09).toContain('"CANCEL"');
    expect(ui09).toContain("familyApi.checkInTodayTask");
    expect(ui09).toContain("operationFor(`checkin-${remoteAction.task_id}-v${remoteAction.task_version}`)");
    expect(ui09).toContain("completeAction(reflection)");
  });

  it("uses Bearer-safe Family API commands with correlation and idempotency metadata", () => {
    expect(client).toContain("/growth/journey-plans/${planId}/phase-review");
    expect(client).toContain("/growth/actions/today");
    expect(client).toContain("/families/${familyId}/today");
    expect(client).toContain("/tasks/${taskId}/state");
    expect(client).toContain("/tasks/${taskId}/check-in");
    expect(client).toContain('"idempotency-key": idempotencyKey');
    expect(client).toContain('"x-source": "family-ai-mobile"');
  });
});
