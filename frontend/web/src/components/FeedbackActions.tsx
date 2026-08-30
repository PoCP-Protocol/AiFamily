type Props = {
  disabled: boolean;
  onHelpful: () => void;
  onNotHelpful: () => void;
};

export function FeedbackActions({ disabled, onHelpful, onNotHelpful }: Props) {
  return (
    <div className="feedback-actions" aria-label="草案反馈">
      <span className="feedback-label">这份理解贴近你的情况吗？</span>
      <button type="button" className="secondary-button" disabled={disabled} onClick={onHelpful}>有帮助</button>
      <button type="button" className="secondary-button" disabled={disabled} onClick={onNotHelpful}>不太贴合</button>
    </div>
  );
}
