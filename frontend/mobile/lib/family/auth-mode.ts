export type FamilyAuthMode = "development" | "test" | "production";

export function parseFamilyAuthMode(value: string | undefined): FamilyAuthMode {
  const normalized = value?.trim().toLowerCase();
  if (normalized === "development" || normalized === "dev" || normalized === "local") return "development";
  if (normalized === "test") return "test";
  return "production";
}

export function allowsDevAccountSession(mode: FamilyAuthMode) {
  return mode === "development" || mode === "test";
}
