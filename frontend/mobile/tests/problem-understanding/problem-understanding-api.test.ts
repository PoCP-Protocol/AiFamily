import { describe, expect, it } from "vitest";

import {
  type GeneratedUnderstandingResponse,
  confirmUnderstanding,
  recordUnderstandingView,
  toUnderstandingReceipt,
  toUnderstandingDraft,
  toViewedDraftBinding,
} from "../../features/problem-understanding/api";
import { FamilyApiClient } from "../../lib/family/family-api-client";

function generatedResponse(): GeneratedUnderstandingResponse {
  return {
    run_id: "run-1",
    artifact_hash: "artifact-1",
    request_hash: "request-1",
    provenance_ref: "air-provenance:v1:sha256:provenance-1",
    version: 1,
    prior_draft_artifact_hash: null,
    status: "DRAFT",
    summary: "现在更像是睡前节奏难以衔接，而不是谁不愿意配合。",
    hypotheses: [{ statement: "白天结束得较晚，可能让睡前转换更困难。" }],
    unknowns: [{ question: "周末和工作日是否一样？", reason: "还缺少时间差异" }],
    follow_up_questions: ["周末和工作日是否一样？"],
    strengths: [{ statement: "家长已经开始观察每天节奏的差异。" }],
    desired_change: { statement: "希望晚上能更从容地进入休息。" },
    source_refs: ["guardian-input-1"],
    knowledge_references: ["knowledge-reviewed-1"],
    provider_id: "approved-provider",
    model: "family-model",
    model_version: "2026-09",
    prompt_version: "understanding-v1",
    schema_version: "family_problem_understanding.v1",
    context_snapshot_ref: "context-1",
    provenance: { provider_id: "approved-provider" },
    requires_guardian_confirmation: true,
    may_mutate_business_state: false,
  };
}

describe("generative family-understanding mobile contract", () => {
  it("maps generated content without fabricating a confirmation receipt", () => {
    const draft = toUnderstandingDraft(generatedResponse(), "tenant-1", "family-1");

    expect(draft.summary).toContain("睡前节奏");
    expect(draft.alternativeExplanations).toEqual([
      "白天结束得较晚，可能让睡前转换更困难。",
    ]);
    expect(draft.unknowns[0].label).toBe("周末和工作日是否一样？");
    expect(draft.humanGateReceiptRef).toBeNull();
    expect(draft.provenanceRef).toBe(
      "air-provenance:v1:sha256:provenance-1",
    );
    expect(draft.provenanceRef).not.toBe(generatedResponse().request_hash);
    expect(draft.scopeRef).toBe(
      "family://tenant-1/family-1/problem-understanding",
    );
  });

  it("rejects a response that is not a non-mutating draft", () => {
    expect(() =>
      toUnderstandingDraft(
        { ...generatedResponse(), may_mutate_business_state: true },
        "tenant-1",
        "family-1",
      ),
    ).toThrow("UNDERSTANDING_RESPONSE_INVALID");
  });

  it("posts the adult expression to the real understanding endpoint", async () => {
    const requests: [RequestInfo | URL, RequestInit | undefined][] = [];
    const fetcher: typeof fetch = async (input, init) => {
      requests.push([input, init]);
      return new Response(JSON.stringify(generatedResponse()), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    };
    const client = new FamilyApiClient("http://family-api.test", fetcher);

    await client.generateFamilyUnderstanding(
      "token-1",
      "family-1",
      {
        run_id: "run-1",
        tenant_id: "tenant-1",
        guardian_input_ref: "guardian-input-1",
        guardian_text: "最近很晚还不愿意睡。",
        revision: 1,
        prior_draft_artifact_hash: null,
      },
    );

    expect(requests).toHaveLength(1);
    const [url, request] = requests[0];
    expect(url).toBe(
      "http://family-api.test/v1/families/family-1/understanding-drafts",
    );
    expect(request?.headers).toMatchObject({ Authorization: "Bearer token-1" });
    expect(JSON.parse(String(request?.body))).toMatchObject({
      guardian_text: "最近很晚还不愿意睡。",
      revision: 1,
    });
  });

  it("records VIEWED before confirmation and sends only immutable bindings", async () => {
    const requests: [RequestInfo | URL, RequestInit | undefined][] = [];
    const fetcher: typeof fetch = async (input, init) => {
      requests.push([input, init]);
      return new Response(
        JSON.stringify({
          view_event_ref: "view-1",
          status: "VIEWED",
          scope_ref: "family://tenant-1/family-1/problem-understanding",
          artifact_ref: "artifact-1",
          artifact_version: 1,
          provenance_ref: "air-provenance:v1:sha256:provenance-1",
          viewed_at: "2026-09-01T10:00:00Z",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    };
    const draft = toUnderstandingDraft(generatedResponse(), "tenant-1", "family-1");

    const response = await recordUnderstandingView(
      "http://family-api.test",
      "token-1",
      "family-1",
      draft.reviewedDraftRef,
      {
        artifact_version: draft.draftVersion,
        provenance_ref: draft.provenanceRef,
        view_event_ref: "view-1",
      },
      fetcher,
    );
    const viewed = toViewedDraftBinding(response, {
      signalRef: draft.signalRef,
      signalVersion: draft.signalVersion,
      scopeRef: draft.scopeRef,
      reviewedDraftRef: draft.reviewedDraftRef,
      draftVersion: draft.draftVersion,
      provenanceRef: draft.provenanceRef,
      humanGateReceiptRef: null,
      viewEventRef: null,
    });

    expect(viewed.viewEventRef).toBe("view-1");
    expect(String(requests[0][0])).toContain(
      "/understanding-drafts/artifact-1/views",
    );
    expect(JSON.parse(String(requests[0][1]?.body))).toEqual({
      artifact_version: 1,
      provenance_ref: "air-provenance:v1:sha256:provenance-1",
      view_event_ref: "view-1",
    });
  });

  it("uses the server receipt and never invents a GrowthIntent", async () => {
    const fetcher: typeof fetch = async () =>
      new Response(
        JSON.stringify({
          receipt_ref: "review-receipt:v1:sha256:server",
          status: "EFFECTIVE",
          scope_ref: "family://tenant-1/family-1/problem-understanding",
          artifact_ref: "artifact-1",
          artifact_version: 1,
          provenance_ref: "air-provenance:v1:sha256:provenance-1",
          expires_at: "2026-09-02T10:00:00Z",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    const viewed = {
      signalRef: "understanding:artifact-1",
      signalVersion: 1,
      scopeRef: "family://tenant-1/family-1/problem-understanding",
      reviewedDraftRef: "artifact-1",
      draftVersion: 1,
      provenanceRef: "air-provenance:v1:sha256:provenance-1",
      viewEventRef: "view-1",
    };

    const response = await confirmUnderstanding(
      "http://family-api.test",
      "token-1",
      "family-1",
      "artifact-1",
      {
        artifact_version: 1,
        provenance_ref: viewed.provenanceRef,
        view_event_ref: viewed.viewEventRef,
      },
      fetcher,
    );
    const receipt = toUnderstandingReceipt(response, viewed);

    expect(receipt.humanGateReceiptRef).toBe(
      "review-receipt:v1:sha256:server",
    );
    expect(receipt.growthIntentRef).toBeNull();
  });
});
