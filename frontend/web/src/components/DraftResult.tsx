import type { ExperienceDraft } from "../api/client";
import { FeedbackActions } from "./FeedbackActions";

type Props = {
  draft: ExperienceDraft | null;
  onDelete: () => void;
  onReplay: () => void;
  onHelpful: () => void;
  onNotHelpful: () => void;
  feedbackDisabled: boolean;
};

export function DraftResult({ draft, onDelete, onReplay, onHelpful, onNotHelpful, feedbackDisabled }: Props) {
  if (!draft) {
    return (
      <section className="panel empty-panel" aria-labelledby="draft-heading">
        <div className="section-kicker">N1 · 理解草案</div>
        <h2 id="draft-heading">这里会出现一份可核对的草案</h2>
        <p className="muted">提交表达后，AI 的理解、证据边界与下一步会在这里分开呈现。</p>
      </section>
    );
  }

  return (
    <section className="panel" aria-labelledby="draft-heading">
      <div className="result-header">
        <div>
          <div className="section-kicker">N1 · 理解草案</div>
          <h2 id="draft-heading">这不是事实结论</h2>
        </div>
        <span className="draft-badge">DRAFT</span>
      </div>
      <div className="draft-copy">
        <h3>我对这段表达的暂时理解</h3>
        <p>{draft.output.understanding}</p>
        <h3>可以先做什么</h3>
        <p>{draft.output.next_step}</p>
      </div>
      <div className="callout">
        <strong>请在采用前核对</strong>
        <ul>
          {draft.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
        </ul>
      </div>
      <dl className="provenance-grid">
        <div><dt>provenance</dt><dd>{draft.provenance.provenance_ref}</dd></div>
        <div><dt>model attempt</dt><dd>{draft.provenance.model_attempt_ref}</dd></div>
        <div><dt>context snapshot</dt><dd>{draft.provenance.context_snapshot_ref}</dd></div>
        <div><dt>evidence</dt><dd>{draft.provenance.kind === "SYNTHETIC_TEST" ? "测试夹具" : "AI 草案"}</dd></div>
      </dl>
      {draft.benchmark ? (
        <div className="benchmark-note" aria-label="离线评估参考">
          <strong>离线评估参考（不是家庭或孩子成绩）</strong>
          <span>案例 {draft.benchmark.benchmark_case_version} · 模型 {draft.benchmark.model_version}</span>
          <span>{draft.benchmark.benchmark_gate_status === "BLOCKED" ? "当前不可运行，仅供研究" : `闸门：${draft.benchmark.benchmark_gate_status}`}</span>
        </div>
      ) : null}
      {draft.media_inputs.length > 0 ? (
        <p className="media-note">已关联 {draft.media_inputs.length} 个受保护图片引用，可随时删除。</p>
      ) : null}
      <div className="result-actions">
        <button className="secondary-button" type="button" onClick={onReplay}>打开体验回放</button>
        <button className="text-button" type="button" onClick={onDelete}>删除这次体验及媒体引用</button>
      </div>
      <div className="feedback-divider" />
      <FeedbackActions disabled={feedbackDisabled} onHelpful={onHelpful} onNotHelpful={onNotHelpful} />
    </section>
  );
}
