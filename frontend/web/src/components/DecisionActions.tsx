type Props = {
  disabled: boolean;
  onConfirm: () => void;
  onReject: () => void;
  onRewrite: () => void;
  onHuman: () => void;
};

export function DecisionActions({ disabled, onConfirm, onReject, onRewrite, onHuman }: Props) {
  return (
    <section className="panel actions-panel" aria-labelledby="actions-heading">
      <div className="section-kicker">N2 · 家庭确认</div>
      <h2 id="actions-heading">由你决定下一步</h2>
      <div className="action-grid">
        <button type="button" className="primary-button" disabled={disabled} onClick={onConfirm}>确认并请求继续</button>
        <button type="button" className="secondary-button" disabled={disabled} onClick={onRewrite}>改写草案</button>
        <button type="button" className="secondary-button" disabled={disabled} onClick={onReject}>暂不采用</button>
        <button type="button" className="human-button" disabled={disabled} onClick={onHuman}>请求人工顾问</button>
      </div>
      <p className="muted action-note">确认只会提交人工闸门请求，不会自动写入家庭事实。</p>
    </section>
  );
}
