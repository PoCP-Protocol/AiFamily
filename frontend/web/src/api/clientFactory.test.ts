import { describe, expect, it } from "vitest";
import { createDefaultExperienceApiClient, resolveExperienceClientMode } from "./clientFactory";
import { HttpExperienceApiClient } from "./httpClient";

describe("experience client factory", () => {
  it("keeps the local sandbox fake client as the implicit development default", () => {
    expect(resolveExperienceClientMode({ DEV: true })).toBe("fake");
    expect(resolveExperienceClientMode({ DEV: false })).toBe("http");
  });

  it("allows an explicit HTTP client in development for API contract smoke tests", () => {
    expect(resolveExperienceClientMode({ DEV: true, VITE_EXPERIENCE_CLIENT: "http" })).toBe("http");
    expect(createDefaultExperienceApiClient({ DEV: true, VITE_EXPERIENCE_CLIENT: "http" }))
      .toBeInstanceOf(HttpExperienceApiClient);
  });

  it("allows an explicit fake client without changing production defaults", () => {
    expect(resolveExperienceClientMode({ DEV: false, VITE_EXPERIENCE_CLIENT: "fake" })).toBe("fake");
    expect(createDefaultExperienceApiClient({ DEV: false, VITE_EXPERIENCE_CLIENT: "fake" }))
      .not.toBeInstanceOf(HttpExperienceApiClient);
  });

  it("fails closed to HTTP for unknown configuration values in production", () => {
    expect(resolveExperienceClientMode({ DEV: false, VITE_EXPERIENCE_CLIENT: "unexpected" })).toBe("http");
  });
});
