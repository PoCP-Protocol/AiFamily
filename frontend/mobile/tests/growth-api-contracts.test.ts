import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

describe("growth/journey Mobile contract", () => {
  const source = readFileSync(resolve(process.cwd(), "lib/family/growth-api-contracts.ts"), "utf8");

  it("distinguishes mounted routes from production readiness", () => {
    expect(source).toContain("routes now exist in FastAPI");
    expect(source).toContain("identity/consent wiring remain fail-closed");
    expect(source).toContain("not evidence that the capability is production-ready");
  });

  it("keeps journey activation and human review as named states", () => {
    expect(source).toContain('"DRAFT" | "ACTIVE" | "PAUSED" | "COMPLETED"');
    expect(source).toContain('"CONTINUE" | "ADJUST" | "PAUSE" | "HUMAN_REVIEW_REQUIRED"');
  });

  it("defines UI-05 as a private process projection, never a growth score", () => {
    expect(source).toContain('projection_version: "UI05_SERVICE_JOURNEY_V1"');
    expect(source).toContain('visibility: "FAMILY_PRIVATE"');
    expect(source).toContain('boundary: "PROCESS_PROJECTION_NOT_SCORE_OR_OUTCOME"');
    expect(source).toContain('"SERVICE_JOURNEY_IS_PRIVATE_PROCESS_SUPPORT_NOT_GROWTH_OUTCOME"');
  });
});
