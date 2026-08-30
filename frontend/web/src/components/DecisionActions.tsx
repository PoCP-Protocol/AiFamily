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
      <div className="section-kicker">你来决定</div>
      <h2 id="actions-heading">这张支持卡贴近你吗？</h2>
      <div className="action-grid">
        <button type="button" className="primary-button" disabled={disabled} onClick={onConfirm}>贴近，先这样试试</button>
        <button type="button" className="secondary-button" disabled={disabled} onClick={onRewrite}>我想再改一改</button>
        <button type="button" className="secondary-button" disabled={disabled} onClick={onReject}>先放一放</button>
        <button type="button" className="human-button" disabled={disabled} onClick={onHuman}>请人工帮我看</button>
      </div>
      <p className="muted action-note">你的选择只用于继续这次体验，不会替你改变家庭内容。</p>
    </section>
  );
}
