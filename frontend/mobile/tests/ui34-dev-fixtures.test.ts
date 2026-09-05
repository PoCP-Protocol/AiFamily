import { describe, expect, it } from "vitest";

import {
  UI34_SCENARIO_FIXTURES,
  getUiScenarioFixture,
  getUiScenarioFixtureCounts,
  getUiScenarioFixtureForPathname,
} from "../dev-fixtures/ui34-scenario";
import { FAMILY_SCREENS } from "../lib/family/ui-registry";

describe("34-screen development scenario fixtures", () => {
  it("provides exactly one fixture for every registered UI", () => {
    expect(UI34_SCENARIO_FIXTURES.map((item) => item.uiId)).toEqual(FAMILY_SCREENS.map((item) => item.id));
    expect(new Set(UI34_SCENARIO_FIXTURES.map((item) => item.uiId)).size).toBe(34);
  });

  it("keeps all simulated records explicitly isolated and side-effect free", () => {
    for (const fixture of UI34_SCENARIO_FIXTURES) {
      expect(fixture.fixtureOnly).toBe(true);
      expect(fixture.externalEffect).toBe(false);
      expect(fixture.facts.length).toBeGreaterThanOrEqual(3);
      expect(fixture.headline.length).toBeGreaterThan(0);
      expect(fixture.nextAction.length).toBeGreaterThan(0);
    }
  });

  it("never introduces family scores, rankings, diagnosis, or automatic payment claims", () => {
    const serialized = JSON.stringify(UI34_SCENARIO_FIXTURES);
    expect(serialized).not.toMatch(/家庭总分|家庭排名|自动扣款成功|确诊|疗效/);
  });

  it("supports looking up the development fixture for a screen", () => {
    expect(getUiScenarioFixture("UI-21")?.state).toBe("DRAFT");
    expect(getUiScenarioFixture("UI-99")).toBeUndefined();
  });

  it("matches the fixture to its application route", () => {
    expect(getUiScenarioFixtureForPathname("/")?.uiId).toBe("UI-01");
    expect(getUiScenarioFixtureForPathname("/ui/UI-21")?.uiId).toBe("UI-21");
    expect(getUiScenarioFixtureForPathname("/dev/data-lab")).toBeUndefined();
  });

  it("reports stable counts for the data-lab filters", () => {
    const counts = getUiScenarioFixtureCounts();
    expect(counts.ALL).toBe(34);
    expect(counts.READY + counts.DRAFT + counts.REVIEW).toBe(counts.ALL);
    expect(counts).toEqual({ ALL: 34, READY: 21, DRAFT: 10, REVIEW: 3 });
  });
});
