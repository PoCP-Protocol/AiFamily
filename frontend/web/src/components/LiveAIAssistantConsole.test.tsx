import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LiveAIAssistantConsole } from "./LiveAIAssistantConsole";

afterEach(() => vi.unstubAllGlobals());

describe("LiveAIAssistantConsole", () => {
  it("fails closed without a sandbox provider", () => {
    render(<LiveAIAssistantConsole />);
    expect(screen.getByRole("alert")).toHaveTextContent("AI Sandbox 未连接");
    expect(screen.queryByRole("button", { name: "生成 AI 草案" })).not.toBeInTheDocument();
  });

  it("generates a draft and records a human edit", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(draft("DRAFT")))
      .mockResolvedValueOnce(response(draft("EDITED_DRAFT", "人工修订：摘要草案")));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<LiveAIAssistantConsole aiBaseUrl="http://127.0.0.1:55305" />);

    await user.click(screen.getByRole("button", { name: "生成 AI 草案" }));
    expect(await screen.findByText("摘要草案")).toBeInTheDocument();
    expect(screen.getByText("问题场景")).toBeInTheDocument();
    expect(screen.getByText("需人工核对")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "人工编辑后保留" }));
    expect(await screen.findByText("人工修订：摘要草案")).toBeInTheDocument();
    expect(screen.getByText("EDITED_DRAFT")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not render an unsafe response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({
      ...draft("DRAFT"),
      fact_write: true,
    })));
    const user = userEvent.setup();
    render(<LiveAIAssistantConsole aiBaseUrl="http://127.0.0.1:55305" />);
    await user.click(screen.getByRole("button", { name: "生成 AI 草案" }));
    expect(await screen.findByText("生成已停止，没有产生草案或外部效果。")).toBeInTheDocument();
    expect(screen.queryByLabelText("AI 直播草案")).not.toBeInTheDocument();
  });

  it("renders a replayable audio-video-ASR-OCR timeline", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(timeline())));
    const user = userEvent.setup();
    render(<LiveAIAssistantConsole aiBaseUrl="http://127.0.0.1:55305" />);

    await user.click(screen.getByRole("button", { name: "生成多模态时间轴" }));

    expect(await screen.findByLabelText("多模态直播时间轴")).toBeInTheDocument();
    expect(screen.getByText("audio + video + transcript + ocr")).toBeInTheDocument();
    expect(screen.getByText("先复述对方的感受")).toBeInTheDocument();
    expect(screen.getByText("课件 OCR：事实 ≠ 评价")).toBeInTheDocument();
    expect(screen.getByText(/不写家庭事实/)).toBeInTheDocument();
  });
});

function response(payload: unknown) {
  return { ok: true, json: async () => payload } as Response;
}

function draft(status: string, summary = "摘要草案") {
  return {
    draft_ref: "draft.synthetic.1",
    summary,
    chapters: ["问题场景", "专家方法"],
    risk_flags: ["需人工核对"],
    status,
    provenance_ref: "provenance.synthetic.1",
    draft_hash: "hash",
    source: "SANDBOX_SYNTHETIC",
    fixture_only: true,
    external_effect: false,
    fact_write: false,
  };
}

function timeline() {
  return {
    timeline_ref: "timeline.synthetic.1",
    session_ref: "live.synthetic.1",
    media_ref: "media.synthetic.1",
    cues: [{
      start_ms: 0,
      end_ms: 5_000,
      speaker_ref: "expert.synthetic.1",
      transcript: "先复述对方的感受",
      frame_ref: "frame.synthetic.1",
      scene_ref: "scene.synthetic.1",
      ocr_text: ["事实 ≠ 评价"],
      evidence_refs: ["asr.synthetic.1", "video.synthetic.1", "ocr.synthetic.1"],
    }],
    evidence_digest: "0123456789abcdef0123456789abcdef",
    modalities: ["audio", "video", "transcript", "ocr"],
    risk_flags: [],
    status: "DRAFT",
    human_review_required: true,
    may_mutate_business_state: false,
    source: "SANDBOX_SYNTHETIC",
    fixture_only: true,
    external_effect: false,
  };
}
