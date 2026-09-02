import { describe, expect, it } from "vitest";

import {
  buildMultimodalDraftRequest,
  type MultimodalDraftResponse,
  toUnderstandingDraft,
} from "../../features/problem-understanding/api";
import { FamilyApiClient } from "../../lib/family/family-api-client";

function generatedResponse(): MultimodalDraftResponse {
  return {
    run_id: "run-1",
    draft_id: "draft-1",
    provenance_ref: "provenance-1",
    status: "DRAFT",
    output: {
      summary: "现在更像是睡前节奏难以衔接，而不是谁不愿意配合。",
      hypotheses: ["白天结束得较晚，可能让睡前转换更困难。"],
      unknowns: ["周末和工作日是否一样？"],
      follow_up_questions: ["最近一次顺利入睡是什么时候？"],
      strengths: ["家长已经开始观察每天节奏的差异。"],
      desired_change: "希望晚上能更从容地进入休息。",
    },
    requires_human_confirmation: true,
    context_snapshot_ref: "context-1",
    context_snapshot_expires_at: "2026-09-03T11:00:00Z",
    provenance: {
      schema_version: "family-understanding-draft.v1",
      generated_at: "2026-09-03T10:00:00Z",
    },
  };
}

describe("S3 multimodal family-understanding mobile contract", () => {
  it("maps only durable server draft and provenance references", () => {
    const draft = toUnderstandingDraft(
      generatedResponse(),
      "tenant-1",
      "family-1",
      2,
      1,
    );

    expect(draft.runId).toBe("run-1");
    expect(draft.reviewedDraftRef).toBe("draft-1");
    expect(draft.provenanceRef).toBe("provenance-1");
    expect(draft.draftVersion).toBe(2);
    expect(draft.summary).toContain("睡前节奏");
    expect(draft.unknowns[0].label).toBe("周末和工作日是否一样？");
    expect(draft.sourceSummary).toContain("1 张已授权图片");
    expect(draft.humanGateReceiptRef).toBeNull();
  });

  it.each([
    { draft_id: null },
    { provenance_ref: null },
    { output: { ...generatedResponse().output, hypotheses: [] } },
  ])("rejects an incomplete durable response: %o", (change) => {
    expect(() =>
      toUnderstandingDraft(
        { ...generatedResponse(), ...change },
        "tenant-1",
        "family-1",
        1,
        0,
      ),
    ).toThrow("UNDERSTANDING_RESPONSE_INVALID");
  });

  it("builds a reference-only text and image request without raw media", () => {
    const request = buildMultimodalDraftRequest({
      runId: "run-1",
      sessionId: "session-1",
      expression: "最近一写作业就会吵起来。",
      revision: 1,
      attachments: [
        {
          mediaType: "IMAGE",
          uri: "media:family/photo-1",
          mimeType: "image/jpeg",
          sha256: "a".repeat(64),
        },
      ],
    });

    expect(request.modalities).toEqual(["TEXT", "IMAGE"]);
    expect(request.input_refs).toEqual(["media:family/photo-1"]);
    expect(request.media_inputs[0]).toEqual({
      media_type: "IMAGE",
      uri: "media:family/photo-1",
      mime_type: "image/jpeg",
      sha256: "a".repeat(64),
    });
    expect(JSON.stringify(request)).not.toContain("base64");
  });

  it("calls create, rewrite, human-review, delete, and replay endpoints", async () => {
    const requests: [RequestInfo | URL, RequestInit | undefined][] = [];
    const fetcher: typeof fetch = async (input, init) => {
      requests.push([input, init]);
      return new Response(JSON.stringify({ status: "recorded" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    };
    const client = new FamilyApiClient("http://family-api.test", fetcher);
    const request = buildMultimodalDraftRequest({
      runId: "run-1",
      sessionId: "session-1",
      expression: "最近很晚还不愿意睡。",
      revision: 1,
      attachments: [],
    });

    await client.createMultimodalUnderstandingDraft(
      "token-1",
      "family-1",
      request,
      "create-1",
    );
    await client.decideMultimodalUnderstandingRun(
      "token-1",
      "family-1",
      "run-1",
      { decision: "rewrite", replacement_text: "更像是遇到不会的题。" },
      "rewrite-1",
    );
    await client.requestMultimodalHumanReview(
      "token-1",
      "family-1",
      "run-1",
      { reason: "请人工核对" },
      "human-1",
    );
    await client.deleteMultimodalUnderstandingRun(
      "token-1",
      "family-1",
      "run-1",
      { reason: "家长删除" },
      "delete-1",
    );
    await client.replayMultimodalUnderstandingRun(
      "token-1",
      "family-1",
      "run-1",
    );

    expect(requests.map(([url]) => String(url))).toEqual([
      "http://family-api.test/families/family-1/experience/multimodal/drafts",
      "http://family-api.test/families/family-1/experience/multimodal/runs/run-1/decisions",
      "http://family-api.test/families/family-1/experience/multimodal/runs/run-1/human-review",
      "http://family-api.test/families/family-1/experience/multimodal/runs/run-1",
      "http://family-api.test/families/family-1/experience/multimodal/runs/run-1/replay",
    ]);
    expect(requests[3][1]?.method).toBe("DELETE");
    expect(requests[3][1]?.headers).toMatchObject({
      Authorization: "Bearer token-1",
      "idempotency-key": "delete-1",
    });
  });
});
