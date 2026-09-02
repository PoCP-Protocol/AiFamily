import { describe, expect, it } from "vitest";

import {
  buildMultimodalDraftRequest,
  toUnderstandingDraft,
  type MultimodalDraftResponse,
  type MultimodalRunInteractionResponse,
  type MultimodalRunReplayResponse,
} from "../../features/problem-understanding/api";
import { FamilyApiClient } from "../../lib/family/family-api-client";

const baseUrl = process.env.S3_HTTP_BASE_URL;
const runHttpTest = baseUrl ? it : it.skip;

describe("S3 family_api HTTP contract", () => {
  runHttpTest(
    "maps a real response and completes review and deletion",
    async () => {
      const client = new FamilyApiClient(baseUrl);
      const session = await client.issueDevAccountSession(
        "s3-mobile-http-contract",
      );
      const contexts = await client.getContexts(session.token);
      const family = contexts.contexts[0];
      expect(family).toBeDefined();

      const runId = `s3-mobile-${Date.now()}`;
      const response =
        await client.createMultimodalUnderstandingDraft<MultimodalDraftResponse>(
          session.token,
          family.family_id,
          buildMultimodalDraftRequest({
            runId,
            sessionId: `session-${runId}`,
            expression: "每天一到写作业，我们就容易因为催促吵起来。",
            revision: 1,
            conversationTurns: [
              {
                inputRef: `input:${runId}`,
                kind: "CONCERN",
                text: "每天一到写作业，我们就容易因为催促吵起来。",
                createdAt: new Date().toISOString(),
              },
            ],
            priorRunId: null,
            attachments: [
              {
                mediaType: "IMAGE",
                uri: "asset:sandbox/family-homework-transition-v1",
                mimeType: "image/png",
                sha256: "b".repeat(64),
              },
            ],
          }),
          `create:${runId}`,
        );

      const draft = toUnderstandingDraft(
        response,
        family.tenant_id,
        family.family_id,
        {
          revision: 1,
          mediaCount: 1,
          sourceRefs: [
            `input:${runId}`,
            "asset:sandbox/family-homework-transition-v1",
          ],
        },
      );
      expect(draft.runId).toBe(runId);
      expect(draft.reviewedDraftRef).toBe(`draft:${runId}`);
      expect(draft.summary).toContain("作业");
      expect(draft.mediaCount).toBe(1);

      const humanReview =
        await client.requestMultimodalHumanReview<MultimodalRunInteractionResponse>(
          session.token,
          family.family_id,
          runId,
          { reason: "家长希望人工核对这份理解。" },
          `human-review:${runId}`,
        );
      expect(humanReview.run_id).toBe(runId);

      const deleted =
        await client.deleteMultimodalUnderstandingRun<MultimodalRunInteractionResponse>(
          session.token,
          family.family_id,
          runId,
          { reason: "家长删除本次家庭理解草案。" },
          `delete:${runId}`,
        );
      expect(deleted.run_id).toBe(runId);

      const replay =
        await client.replayMultimodalUnderstandingRun<MultimodalRunReplayResponse>(
          session.token,
          family.family_id,
          runId,
        );
      expect(replay.deletion_state).toBe("deleted");
      expect(replay.draft_payload).toBeNull();
      expect(replay.artifact_refs).toEqual([]);
    },
  );
});
