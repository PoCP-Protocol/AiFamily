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
      understanding: {
        lived_experience:
          "每天到了睡前，你既担心孩子休息不够，又不想把晚上变成反复催促。",
        central_tension:
          "尽快入睡的现实压力，与孩子从活动切换到休息所需的节奏发生了冲突。",
        care_intent:
          "你真正想守护的是孩子的睡眠，也希望晚上的关系是平静而亲近的。",
      },
      hypotheses: [
        {
          hypothesis_id: "H1",
          statement: "白天结束得较晚，可能让睡前转换更困难。",
          rationale: "从高唤醒活动直接进入睡眠，往往需要更清晰的过渡信号。",
          evidence: [
            {
              source_type: "PARENT_TEXT",
              source_ref: "input:run-1",
              observation: "家长描述最近很晚仍不愿意睡。",
            },
          ],
          knowledge_refs: ["knowledge:sleep-transition-v1"],
          confidence: "MEDIUM",
          disconfirming_evidence_needed:
            "需要了解白天结束较早时是否仍然同样困难。",
        },
      ],
      unknowns: [
        {
          unknown_id: "U1",
          description: "周末和工作日的睡前情况是否一样",
          why_it_matters: "这有助于判断主要影响来自固定节奏还是当天活动强度",
          related_hypothesis_ids: ["H1"],
        },
      ],
      follow_up_questions: [
        {
          question_id: "Q1",
          question: "最近一次顺利入睡是什么时候？",
          purpose: "寻找已经有效的家庭条件，而不是只盯着困难",
          answers_unknown_ids: ["U1"],
        },
      ],
      strengths: [
        {
          statement: "你已经开始观察每天节奏的差异。",
          evidence_refs: ["input:run-1"],
          why_it_matters: "这种观察能帮助家庭找到真正可调整的环节。",
        },
      ],
      desired_change: {
        statement: "希望晚上能更从容地进入休息。",
        basis: "EXPLICIT",
        observable_signs: ["提醒次数减少", "睡前能够完成一次平静的协商"],
        confirmation_question: "这是不是你最希望先看到的变化？",
      },
      limitations: ["目前只有家长的描述，还不知道孩子如何体验睡前时刻。"],
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
    expect(draft.summary).toContain("反复催促");
    expect(draft.centralTension).toContain("现实压力");
    expect(draft.unknowns[0].label).toContain("周末和工作日");
    expect(draft.followUpQuestions[0]).toContain("顺利入睡");
    expect(draft.limitations).toHaveLength(1);
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
    expect(request).not.toHaveProperty("output_schema");
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
