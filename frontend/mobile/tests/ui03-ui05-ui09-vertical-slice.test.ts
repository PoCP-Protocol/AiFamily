import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { createSyntheticMultimodalAdapter } from "../lib/family/multimodal-api-contracts";

const ui03 = readFileSync(resolve(process.cwd(), "app/ui/UI-03.tsx"), "utf8");
const ui05 = readFileSync(resolve(process.cwd(), "app/ui/UI-05.tsx"), "utf8");
const ui09 = readFileSync(resolve(process.cwd(), "app/ui/UI-09.tsx"), "utf8");
const growthContracts = readFileSync(resolve(process.cwd(), "lib/family/growth-api-contracts.ts"), "utf8");
const mediaContracts = readFileSync(resolve(process.cwd(), "lib/family/multimodal-api-contracts.ts"), "utf8");

describe("UI-03 → UI-05 → UI-09 family need vertical experience", () => {
  it("keeps the emotional-first path before explanation, small action, feedback and next step", () => {
    expect(ui03).toContain("先接住这份无奈和疲惫");
    expect(ui03).toContain('router.push("/ui/UI-04" as Href)');
    expect(ui05).toContain("先一起走一步");
    expect(ui05).toContain('router.push("/ui/UI-09" as Href)');
    expect(ui09).toContain("今晚只做一件小事");
    expect(ui09).toContain("完成、暂停、跳过或稍后再来");
  });

  it("renders loading, empty, denied, error, review/paused and confirmation states", () => {
    for (const state of ["loading", "empty", "denied", "error"]) {
      expect(ui03).toContain(`remoteState === "${state}"`);
      expect(ui05).toContain(`loadState === "${state}"`);
      if (state !== "empty") expect(ui09).toContain(`remoteState === "${state}"`);
    }
    expect(ui03).toContain('remoteState === "review_required"');
    expect(ui03).toContain("CONSENT_REQUIRED");
    expect(ui05).toContain('setReviewOutcome(decision === "CONTINUE" ? "success" : "paused")');
    expect(ui09).toContain('setSyncState("success")');
    expect(ui09).toContain('setSyncState(action === "PAUSE" ? "paused" : "idle")');
  });

  it("does not manufacture completed facts when an API projection is absent", () => {
    expect(ui03).not.toContain("PREVIEW_SCORECARD");
    expect(ui03).toContain("这里不会预填家庭分数");
    expect(ui03).not.toContain("overall_score");
    expect(ui03).not.toContain("peer_reference");
    expect(ui03).not.toContain("GrowthRadarOverview");
    expect(ui05).toContain("remote?.weekly_tasks?.length");
    expect(ui05).toContain("不会预填完成状态");
    expect(ui05).toContain("remote ? `已记录 ${progress.completed} 项过程` : \"等待真实过程记录\"");
    expect(ui09).toContain("只展示服务端确认过的任务");
    expect(ui09).toContain('connected ? remoteAction?.assignment_text ?? "等待服务端确认行动"');
    expect(ui09).toContain("useLocalSyntheticAction");
  });

  it("keeps the server-owned Journey and task contract explicit", () => {
    expect(growthContracts).toContain("weekly_tasks?");
    expect(growthContracts).toContain("PROCESS_PROJECTION_NOT_SCORE_OR_OUTCOME");
    expect(ui05).toContain("familyApi.getServiceJourney");
    expect(ui05).toContain("familyApi.getJourneyPlan");
    expect(ui09).toContain("getFamilyToday");
    expect(ui09).toContain("familyApi.checkInTodayTask");
  });

  it("reserves a unified multimodal contract for text, voice, image, audio, video and cards", () => {
    for (const kind of ["TEXT", "VOICE", "IMAGE", "AUDIO", "VIDEO", "INTERACTIVE_CARD"]) expect(mediaContracts).toContain(kind);
    for (const state of ["CONSENT_REQUIRED", "UPLOADING", "TRANSCRIBING", "OCR_PROCESSING", "PLAYBACK_FAILED", "LOW_BANDWIDTH", "REJECTED"]) expect(mediaContracts).toContain(state);
    expect(mediaContracts).toContain("synthetic");
    expect(mediaContracts).toContain("MultimodalDraftResponse");
    expect(ui05).toContain("转写、OCR 和播放");
    expect(ui09).toContain("媒体上传、转写、OCR 和播放");
  });

  it("uses the same consent-gated shape for synthetic media in test", async () => {
    const adapter = createSyntheticMultimodalAdapter();
    const consent = await adapter.requestConsent("VOICE");
    const attachment = await adapter.upload({ kind: "VOICE", uri: "synthetic://voice-1", consent_ref: consent.consent_ref });
    expect(attachment.synthetic).toBe(true);
    expect(attachment.status).toBe("READY");
    expect((await adapter.getProjection()).attachments).toHaveLength(1);
  });
});
