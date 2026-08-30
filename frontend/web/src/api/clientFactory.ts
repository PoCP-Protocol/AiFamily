import type { ExperienceApiClient } from "./client";
import { createFakeExperienceApiClient } from "./fakeClient";
import { HttpExperienceApiClient } from "./httpClient";

export type ExperienceClientMode = "fake" | "http";

export type ExperienceClientEnvironment = {
  DEV?: boolean;
  VITE_EXPERIENCE_CLIENT?: string;
  VITE_API_BASE_URL?: string;
};

/**
 * Resolve the client mode from an explicit setting, retaining the local
 * sandbox default for developers and the HTTP default for production builds.
 */
export const resolveExperienceClientMode = (
  environment: ExperienceClientEnvironment,
): ExperienceClientMode => {
  if (environment.VITE_EXPERIENCE_CLIENT === "fake") return "fake";
  if (environment.VITE_EXPERIENCE_CLIENT === "http") return "http";
  return environment.DEV === true ? "fake" : "http";
};

export const createDefaultExperienceApiClient = (
  environment: ExperienceClientEnvironment,
): ExperienceApiClient => {
  if (resolveExperienceClientMode(environment) === "fake") {
    return createFakeExperienceApiClient();
  }

  return new HttpExperienceApiClient({
    baseUrl: environment.VITE_API_BASE_URL,
  });
};
