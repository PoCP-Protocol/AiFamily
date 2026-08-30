import type { ExperienceDraft } from "../api/client";
import { FeedbackActions } from "./FeedbackActions";

type Props = {
  draft: ExperienceDraft | null;
  expression: string;
  onDelete: () => void;
  onReplay: () => void;
  onHelpful: () => void;
  onNotHelpful: () => void;
  onChooseStep: () => void;
  onCorrect: () => void;
  feedbackDisabled: boolean;
};

export function DraftResult({ draft, expression, onDelete, onReplay, onHelpful, onNotHelpful, onChooseStep, onCorrect, feedbackDisabled }: Props) {
  if (!draft) {
    return (
      <section className="panel empty-panel" aria-labelledby="draft-heading">
        <div className="section-kicker">第 2 步 · 看见重点</div>
        <h2 id="draft-heading">这里会出现一张家庭支持卡</h2>
        <p className="muted">提交一件小事后，我们会把听到的重点、仍不确定的地方和今晚的一小步放在一起。</p>
      </section>
    );
  }

  return (
    <section className="panel" aria-labelledby="draft-heading">
      <div className="result-header">
        <div>
          <div className="section-kicker">第 2 步 · 家庭支持卡</div>
          <h2 id="draft-heading">我们先把这件事放在这里</h2>
        </div>
        <span className="draft-badge">先一起看看</span>
      </div>
      <div className="support-card-sections">
        <section className="support-card-section">
          <h3>你刚才说的是</h3>
          <p className="quoted-expression">“{expression.trim()}”</p>
        </section>
        <section className="support-card-section">
          <h3>我们目前听到的</h3>
          <p>{draft.output.understanding}</p>
        </section>
        <section className="support-card-section support-card-uncertain">
          <h3>还不确定的地方</h3>
          <ul>
            {draft.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
          </ul>
        </section>
        <section className="support-card-section support-card-step">
          <h3>今晚可以试的一小步</h3>
          <p>{draft.output.next_step}</p>
          <button className="primary-button" type="button" onClick={onChooseStep}>今晚先试这一步</button>
        </section>
        <section className="support-card-section">
          <h3>你来校正或补充</h3>
          <p className="muted">如果哪里不贴合，可以改写这段话，再重新看看。</p>
          <button className="secondary-button" type="button" onClick={onCorrect}>改一改这段话</button>
        </section>
      </div>
      {draft.media_inputs.length > 0 ? (
        <p className="media-note">这次表达里包含你确认过的图片。</p>
      ) : null}
      <div className="feedback-divider" />
      <FeedbackActions disabled={feedbackDisabled} onHelpful={onHelpful} onNotHelpful={onNotHelpful} />
      <details className="secondary-details">
        <summary>更多选择</summary>
        <div className="result-actions">
          <button className="secondary-button" type="button" onClick={onReplay}>看看这次体验的记录</button>
          <button className="text-button" type="button" onClick={onDelete}>删除这次体验</button>
        </div>
      </details>
    </section>
  );
}
