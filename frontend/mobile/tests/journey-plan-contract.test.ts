import { describe, expect, it } from "vitest";

import { FamilyApiError } from "../lib/family/family-api-client";
import { classifyJourneyPlanError, journeyPlanErrorCopy } from "../lib/family/journey-plan-contract";

describe("Journey plan assessment seam contract", () => {
  it("keeps the client DTO transport-only and classifies safe retry paths", async () => {
    const module = await import("../lib/family/journey-plan-contract");
    expect(module).toBeDefined();
    expect(classifyJourneyPlanError(new FamilyApiError("conflict", 409, "JOURNEY_PLAN_CONFLICT", null))).toBe("CONFLICT");
    expect(classifyJourneyPlanError(new FamilyApiError("forbidden", 403, "CONSENT_REQUIRED", null))).toBe("CONSENT_OR_ACCESS_BLOCKED");
    expect(classifyJourneyPlanError(new FamilyApiError("offline", 0, "FAMILY_API_NETWORK_ERROR", null))).toBe("RETRYABLE");
  });

  it("does not turn a missing assessment into an automatic plan creation", () => {
    expect(journeyPlanErrorCopy("ASSESSMENT_REQUIRED")).toContain("先完成家庭测评");
    expect(journeyPlanErrorCopy("NOT_CONFIGURED")).toContain("没有创建任何计划");
  });
});
