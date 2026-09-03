import { useState } from "react";

type Props = { aiBaseUrl?: string };

type Draft = {
  draft_ref: string;
  summary: string;
  chapters: string[];
  risk_flags: string[];
  status: "DRAFT" | "APPROVED_DRAFT" | "EDITED_DRAFT" | "REJECTED_DRAFT";
  provenance_ref: string;
  draft_hash: string;
  source: "SANDBOX_SYNTHETIC";
  fixture_only: true;
  external_effect: false;
  fact_write: false;
};
type TimelineCue = {
  start_ms: number;
  end_ms: number;
  speaker_ref: string;
  transcript: string;
  frame_ref: string | null;
  ocr_text: string[];
  evidence_refs: string[];
};
type MultimodalTimeline = {
  timeline_ref: string;
  cues: TimelineCue[];
  evidence_digest: string;
  modalities: string[];
  risk_flags: string[];
  status: "DRAFT";
  human_review_required: true;
  may_mutate_business_state: false;
  source: "SANDBOX_SYNTHETIC";
  fixture_only: true;
  external_effect: false;
};

const DEFAULT_TRANSCRIPT =
  "专家：冲突发生时，先暂停评价，复述对方刚才表达的感受，再共同确认一个可以完成的小行动。";

export function LiveAIAssistantConsole({ aiBaseUrl }: Props) {
  const [transcript, setTranscript] = useState(DEFAULT_TRANSCRIPT);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [timeline, setTimeline] = useState<MultimodalTimeline | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  return (
    <section className="live-ops-panel live-ai-console" aria-labelledby="live-ai-heading">
      <div className="live-ops-heading">
        <div>
          <span>AI COPILOT · SANDBOX</span>
          <h2 id="live-ai-heading">直播内容助手</h2>
          <p>把合成字幕整理成摘要、章节和风险草案，必须经人工复核。</p>
        </div>
        <strong>{aiBaseUrl ? "GATEWAY READY" : "FAIL-CLOSED"}</strong>
      </div>

      {!aiBaseUrl ? <p role="alert">AI Sandbox 未连接，禁止生成或伪造内容。</p> : null}
      {aiBaseUrl ? (
        <div className="live-ai-workbench">
          <label>
            <span>合成直播字幕</span>
            <textarea
              aria-label="合成直播字幕"
              value={transcript}
              onChange={(event) => setTranscript(event.target.value)}
              rows={5}
            />
          </label>
          <button
            type="button"
            disabled={busy || !transcript.trim()}
            onClick={() => void generate()}
          >
            {busy ? "正在生成…" : "生成 AI 草案"}
          </button>
          <button type="button" disabled={busy} onClick={() => void generateTimeline()}>
            生成多模态时间轴
          </button>
        </div>
      ) : null}

      {timeline ? (
        <article className="live-multimodal-timeline" aria-label="多模态直播时间轴">
          <header>
            <div>
              <span>{timeline.modalities.join(" + ")}</span>
              <h3>音视频证据时间轴</h3>
            </div>
            <small>{timeline.timeline_ref}</small>
          </header>
          <ol>
            {timeline.cues.map((cue) => (
              <li key={`${cue.start_ms}:${cue.evidence_refs.join(":")}`}>
                <time>{formatTime(cue.start_ms)}–{formatTime(cue.end_ms)}</time>
                <div>
                  <strong>{cue.transcript}</strong>
                  {cue.ocr_text.length ? <p>课件 OCR：{cue.ocr_text.join("；")}</p> : null}
                  <small>{cue.frame_ref ?? "无关键帧"} · {cue.evidence_refs.length} 条证据</small>
                </div>
              </li>
            ))}
          </ol>
          {timeline.risk_flags.length ? (
            <p role="alert">风险草案：{timeline.risk_flags.join("、")}，等待人工复核。</p>
          ) : (
            <p>未检测到高影响声明；仍须人工复核后才能使用。</p>
          )}
          <small>证据摘要 {timeline.evidence_digest.slice(0, 16)} · 不写家庭事实</small>
        </article>
      ) : null}

      {draft ? (
        <article className="live-ai-draft" aria-label="AI 直播草案">
          <header>
            <div>
              <span>{draft.status}</span>
              <h3>本场内容沉淀</h3>
            </div>
            <small>{draft.provenance_ref}</small>
          </header>
          <p className="live-ai-summary">{draft.summary}</p>
          <div className="live-ai-columns">
            <div>
              <strong>章节建议</strong>
              <ol>{draft.chapters.map((chapter) => <li key={chapter}>{chapter}</li>)}</ol>
            </div>
            <div>
              <strong>风险提示</strong>
              <ul>{draft.risk_flags.map((risk) => <li key={risk}>{risk}</li>)}</ul>
            </div>
          </div>
          {draft.status === "DRAFT" ? (
            <div className="live-ai-actions">
              <button type="button" onClick={() => void review("APPROVE")}>人工批准草案</button>
              <button type="button" onClick={() => void review("EDIT")}>人工编辑后保留</button>
              <button className="live-ops-reject" type="button" onClick={() => void review("REJECT")}>
                人工拒绝
              </button>
            </div>
          ) : null}
          <small>仅为内容草案 · 不写家庭事实 · 不自动下架 · 无外部副作用</small>
        </article>
      ) : null}
      {message ? <p role="status">{message}</p> : null}
    </section>
  );

  async function generate() {
    if (!aiBaseUrl) return;
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch(`${aiBaseUrl}/sandbox/live-ai/drafts`, {
        method: "POST",
        headers: { ...actorHeaders("AI_OPERATOR"), "Content-Type": "application/json" },
        body: JSON.stringify({
          session_ref: "live.synthetic.1",
          transcript_ref: `transcript.synthetic.${Date.now()}`,
          transcript,
          idempotency_key: `generate:${Date.now()}`,
        }),
      });
      if (!response.ok) throw new Error(`AI generation rejected: ${response.status}`);
      setDraft(parseDraft(await response.json()));
      setMessage("草案已生成，等待人工复核。");
    } catch {
      setDraft(null);
      setMessage("生成已停止，没有产生草案或外部效果。");
    } finally {
      setBusy(false);
    }
  }

  async function review(decision: "APPROVE" | "EDIT" | "REJECT") {
    if (!aiBaseUrl || !draft) return;
    setBusy(true);
    try {
      const response = await fetch(`${aiBaseUrl}/sandbox/live-ai/drafts/${draft.draft_ref}/review`, {
        method: "POST",
        headers: { ...actorHeaders("HUMAN_REVIEWER"), "Content-Type": "application/json" },
        body: JSON.stringify({
          decision,
          reason: "人工核对合成字幕、摘要和风险提示",
          edited_text: decision === "EDIT" ? `人工修订：${draft.summary}` : null,
          idempotency_key: `review:${draft.draft_ref}:${decision}`,
        }),
      });
      if (!response.ok) throw new Error(`Human Gate rejected: ${response.status}`);
      setDraft(parseDraft(await response.json()));
      setMessage(decision === "REJECT" ? "草案已拒绝。" : "人工复核已记录，结果仍不是家庭事实。");
    } catch {
      setMessage("人工复核失败，草案状态没有改变。");
    } finally {
      setBusy(false);
    }
  }

  async function generateTimeline() {
    if (!aiBaseUrl) return;
    setBusy(true);
    setMessage("");
    try {
      const response = await fetch(`${aiBaseUrl}/sandbox/live-ai/multimodal-timelines`, {
        method: "POST",
        headers: { ...actorHeaders("AI_OPERATOR"), "Content-Type": "application/json" },
        body: JSON.stringify(syntheticMultimodalPayload()),
      });
      if (!response.ok) throw new Error(`multimodal timeline rejected: ${response.status}`);
      setTimeline(parseTimeline(await response.json()));
      setMessage("多模态证据已对齐为草案时间轴，等待人工复核。");
    } catch {
      setTimeline(null);
      setMessage("多模态处理已停止，没有生成时间轴或外部效果。");
    } finally {
      setBusy(false);
    }
  }
}

function parseDraft(value: unknown): Draft {
  const record = typeof value === "object" && value !== null
    ? value as Record<string, unknown>
    : null;
  if (
    record === null ||
    typeof record.draft_ref !== "string" ||
    typeof record.summary !== "string" ||
    !Array.isArray(record.chapters) ||
    !Array.isArray(record.risk_flags) ||
    typeof record.provenance_ref !== "string" ||
    typeof record.draft_hash !== "string" ||
    record.source !== "SANDBOX_SYNTHETIC" ||
    record.fixture_only !== true ||
    record.external_effect !== false ||
    record.fact_write !== false ||
    !["DRAFT", "APPROVED_DRAFT", "EDITED_DRAFT", "REJECTED_DRAFT"].includes(String(record.status))
  ) throw new Error("unsafe AI draft");
  return record as Draft;
}

function actorHeaders(role: string): Record<string, string> {
  return {
    "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
    "X-Fixture-Only": "true",
    "X-Tenant-Id": "tenant.synthetic.alpha",
    "X-Family-Id": "family.synthetic.alpha",
    "X-Actor-Id": `actor.synthetic.${role.toLowerCase()}`,
    "X-Actor-Role": role,
  };
}

function parseTimeline(value: unknown): MultimodalTimeline {
  const record = typeof value === "object" && value !== null
    ? value as Record<string, unknown>
    : null;
  if (
    record === null ||
    typeof record.timeline_ref !== "string" ||
    typeof record.evidence_digest !== "string" ||
    !Array.isArray(record.cues) ||
    !Array.isArray(record.modalities) ||
    !Array.isArray(record.risk_flags) ||
    record.status !== "DRAFT" ||
    record.human_review_required !== true ||
    record.may_mutate_business_state !== false ||
    record.source !== "SANDBOX_SYNTHETIC" ||
    record.fixture_only !== true ||
    record.external_effect !== false ||
    record.cues.some((cue) => !isTimelineCue(cue))
  ) throw new Error("unsafe multimodal timeline");
  return record as MultimodalTimeline;
}

function isTimelineCue(value: unknown): value is TimelineCue {
  if (typeof value !== "object" || value === null) return false;
  const cue = value as Record<string, unknown>;
  return Number.isFinite(cue.start_ms) &&
    Number.isFinite(cue.end_ms) &&
    typeof cue.speaker_ref === "string" &&
    typeof cue.transcript === "string" &&
    (cue.frame_ref === null || typeof cue.frame_ref === "string") &&
    Array.isArray(cue.ocr_text) &&
    cue.ocr_text.every((item) => typeof item === "string") &&
    Array.isArray(cue.evidence_refs) &&
    cue.evidence_refs.every((item) => typeof item === "string");
}

function syntheticMultimodalPayload() {
  return {
    session_ref: "live.synthetic.1",
    media_ref: "media.synthetic.mili-lesson",
    audio_ref: "audio.synthetic.mili-lesson",
    video_ref: "video.synthetic.mili-lesson",
    duration_ms: 12_000,
    speech_windows: [
      { start_ms: 0, end_ms: 5_000, confidence: 0.98 },
      { start_ms: 5_000, end_ms: 11_000, confidence: 0.97 },
    ],
    transcript_segments: [
      { start_ms: 0, end_ms: 5_000, text: "先复述对方的感受", speaker_ref: "expert.synthetic.1", confidence: 0.96, evidence_ref: "asr.synthetic.1" },
      { start_ms: 5_000, end_ms: 11_000, text: "再一起确认一个小行动", speaker_ref: "expert.synthetic.1", confidence: 0.95, evidence_ref: "asr.synthetic.2" },
    ],
    video_keyframes: [
      { at_ms: 2_000, frame_ref: "frame.synthetic.1", scene_ref: "scene.synthetic.1", evidence_ref: "video.synthetic.evidence.1" },
      { at_ms: 8_000, frame_ref: "frame.synthetic.2", scene_ref: "scene.synthetic.2", evidence_ref: "video.synthetic.evidence.2" },
    ],
    ocr_observations: [
      { frame_ref: "frame.synthetic.1", text: "事实 ≠ 评价", confidence: 0.94, evidence_ref: "ocr.synthetic.1" },
    ],
    contains_real_person: false,
    contains_biometric_data: false,
    idempotency_key: "multimodal:live.synthetic.1:v1",
  };
}

function formatTime(milliseconds: number): string {
  const seconds = Math.floor(milliseconds / 1_000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
