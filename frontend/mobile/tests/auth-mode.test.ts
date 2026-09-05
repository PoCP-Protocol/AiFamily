import { describe, expect, it } from "vitest";

import { allowsDevAccountSession, parseFamilyAuthMode } from "../lib/family/auth-mode";

describe("Mobile identity mode", () => {
  it("fails closed when the mode is missing or unknown", () => {
    expect(parseFamilyAuthMode(undefined)).toBe("production");
    expect(parseFamilyAuthMode("prod-eu")).toBe("production");
    expect(parseFamilyAuthMode("typo")).toBe("production");
  });

  it("allows development sessions only under an explicit non-production mode", () => {
    expect(allowsDevAccountSession(parseFamilyAuthMode("development"))).toBe(true);
    expect(allowsDevAccountSession(parseFamilyAuthMode("test"))).toBe(true);
    expect(allowsDevAccountSession(parseFamilyAuthMode("production"))).toBe(false);
  });
});
