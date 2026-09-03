import { describe, expect, it } from "vitest";

import { readErrorCode } from "../lib/family/family-api-client";

describe("Family API FastAPI error contract", () => {
  it("preserves domain and authorization codes carried in FastAPI detail", () => {
    expect(readErrorCode({ detail: "family_scope_violation" })).toBe("family_scope_violation");
    expect(readErrorCode({ detail: "consent_required:service:child-1" })).toBe("consent_required:service:child-1");
  });

  it("returns a stable non-sensitive code for Pydantic validation errors", () => {
    expect(readErrorCode({ detail: [{ type: "missing", loc: ["body", "subject_person_id"], msg: "Field required", input: {} }] })).toBe("VALIDATION_MISSING");
  });

  it("supports legacy message/error payloads without overriding FastAPI detail", () => {
    expect(readErrorCode({ detail: "canonical", message: "legacy" })).toBe("canonical");
    expect(readErrorCode({ message: "legacy_message" })).toBe("legacy_message");
    expect(readErrorCode({ error: "legacy_error" })).toBe("legacy_error");
    expect(readErrorCode(null)).toBeNull();
  });
});
