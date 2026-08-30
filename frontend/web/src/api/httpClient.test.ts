import { describe, expect, it } from "vitest";
import { HttpExperienceApiClient } from "./httpClient";

describe("HttpExperienceApiClient", () => {
  it("fails closed until the same-origin Experience API is configured", async () => {
    await expect(new HttpExperienceApiClient().createDraft({} as never, "idem"))
      .rejects.toMatchObject({ code: "PROVIDER_NOT_ADMITTED", status: "refused" });
  });
});
