import { describe, expect, it } from "vitest";
import { createFakeExperienceApiClient } from "./fakeClient";
import type { CreateDraftInput } from "./client";

const input: CreateDraftInput = {
  run_id: "test-run",
  use_case: "family_expression_understanding",
  prompt_version: "experience-studio.v1",
  schema_version: "experience-draft.v1",
  data_class: "FAMILY_PRIVATE_TEXT",
  context_snapshot_ref: "context:test-run",
  payload: { expression: "我们最近总在催促中争吵。" },
  input_refs: [],
  media_inputs: [],
  scope: {
    tenant_id: "tenant",
    region_id: "CN",
    family_id: "family",
    subject_ids: ["guardian"],
    purpose: "family_growth_experience",
    consent_version: "v1",
    consent_granted: true,
    locale: "zh-CN",
  },
};

describe("FakeExperienceApiClient", () => {
  it("returns a synthetic DRAFT with provenance", async () => {
    const draft = await createFakeExperienceApiClient().createDraft(input, "idem-1");
    expect(draft.status).toBe("DRAFT");
    expect(draft.requires_human_confirmation).toBe(true);
    expect(draft.provenance.kind).toBe("SYNTHETIC_TEST");
  });

  it.each([
    ["consent_refused", "CONSENT_REQUIRED"],
    ["provider_not_admitted", "PROVIDER_NOT_ADMITTED"],
    ["deleted", "MEDIA_DELETED"],
  ] as const)("returns governed %s refusal", async (scenario, code) => {
    await expect(createFakeExperienceApiClient(scenario).createDraft(input, "idem-1"))
      .rejects.toMatchObject({ code, status: scenario === "deleted" ? "deleted" : "refused" });
  });

  it("allows a timeout to be retried with the same client", async () => {
    const client = createFakeExperienceApiClient("timeout_then_retry");
    await expect(client.createDraft(input, "idem-1")).rejects.toMatchObject({ code: "TIMEOUT" });
    await expect(client.createDraft(input, "idem-1")).resolves.toMatchObject({ status: "DRAFT" });
  });

  it("keeps human review as a separate receipt", async () => {
    const client = createFakeExperienceApiClient("human_review");
    const draft = await client.createDraft(input, "idem-1");
    const receipt = await client.requestHuman({ run_id: draft.run_id, reason: "需要人工" }, "idem-human");
    expect(receipt.status).toBe("human_review");
  });
});
