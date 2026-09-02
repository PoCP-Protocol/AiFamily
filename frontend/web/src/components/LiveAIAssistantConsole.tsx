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

const DEFAULT_TRANSCRIPT =
  "专家：冲突发生时，先暂停评价，复述对方刚才表达的感受，再共同确认一个可以完成的小行动。";

export function LiveAIAssistantConsole({ aiBaseUrl }: Props) {
  const [transcript, setTranscript] = useState(DEFAULT_TRANSCRIPT);
  const [draft, setDraft] = useState<Draft | null>(null);
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
        </div>
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
