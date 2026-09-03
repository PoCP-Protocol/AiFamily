import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { FORBIDDEN_SERVICE_BODY_FIELDS } from "../lib/family/service-api-contracts";

describe("Python SERVICE Mobile contract", () => {
  const source = readFileSync(resolve(process.cwd(), "lib/family/service-api-contracts.ts"), "utf8");

  it("uses canonical aggregate identifiers for booking", () => {
    expect(source).toContain("service_offering_id: string");
    expect(source).toContain("availability_slot_id: string");
    expect(source).not.toContain("service_offering_version:");
    expect(source).not.toContain("attributes?:");
  });

  it("does not allow a Mobile body to inject scope or authority", () => {
    const bodyBlock = source.slice(source.indexOf("export interface SubmitServiceBookingBody"), source.indexOf("export interface ServiceBookingReceipt"));
    for (const field of FORBIDDEN_SERVICE_BODY_FIELDS) expect(bodyBlock).not.toContain(`${field}:`);
  });

  it("keeps fixture and external-effect truth visible in customer projections", () => {
    expect(source).toContain('environment: "DEV" | "TEST"');
    expect(source).toContain('source_system: "TEST_FIXTURE"');
    expect(source).toContain("external_effect: false");
  });
});
