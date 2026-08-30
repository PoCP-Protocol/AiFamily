type Props = {
  disabled: boolean;
  onHelpful: () => void;
  onNotHelpful: () => void;
};

export function FeedbackActions({ disabled, onHelpful, onNotHelpful }: Props) {
  return (
    <div className="feedback-actions" aria-label="支持卡反馈">
      <span className="feedback-label">这张卡有贴近你吗？</span>
      <button type="button" className="secondary-button" disabled={disabled} onClick={onHelpful}>有贴近</button>
      <button type="button" className="secondary-button" disabled={disabled} onClick={onNotHelpful}>还不太像</button>
    </div>
  );
}
