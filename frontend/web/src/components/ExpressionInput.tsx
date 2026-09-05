import type { CreateDraftInput } from "../api/client";

export type ExpressionForm = Pick<CreateDraftInput, "payload" | "media_inputs" | "scope">;

type Props = {
  value: ExpressionForm;
  disabled: boolean;
  onChange: (value: ExpressionForm) => void;
  onSubmit: () => void;
};

export function ExpressionInput({ value, disabled, onChange, onSubmit }: Props) {
  const image = value.media_inputs[0];
  return (
    <section className="panel" aria-labelledby="expression-heading">
      <div className="section-kicker">N0 · 表达入口</div>
      <h2 id="expression-heading">先把此刻的家庭困扰交给我</h2>
      <p className="muted">文字和图片只作为理解线索。提交后先生成草案，是否采用由你确认。</p>
      <label className="field-label" htmlFor="expression">
        你的表达
      </label>
      <textarea
        id="expression"
        value={value.payload.expression}
        disabled={disabled}
        onChange={(event) =>
          onChange({ ...value, payload: { expression: event.target.value } })
        }
        placeholder="例如：孩子最近写作业很慢，我们每天都因为催促吵起来……"
        rows={6}
      />
      <label className="field-label" htmlFor="image-reference">
        图片引用（可选）
      </label>
      <input
        id="image-reference"
        value={image?.uri ?? ""}
        disabled={disabled}
        onChange={(event) => {
          const uri = event.target.value;
          onChange({
            ...value,
            media_inputs: uri
              ? [{ media_type: "IMAGE", uri, mime_type: "image/*", sha256: "web-reference" }]
              : [],
          });
        }}
        placeholder="受保护的 media:// 引用，不上传原始文件"
      />
      <label className="consent-row">
        <input
          type="checkbox"
          checked={value.scope.consent_granted}
          disabled={disabled}
          onChange={(event) =>
            onChange({
              ...value,
              scope: { ...value.scope, consent_granted: event.target.checked },
            })
          }
        />
        <span>我同意 AiFamily 按本次用途读取这些表达和媒体引用。</span>
      </label>
      <button className="primary-button" type="button" disabled={disabled} onClick={onSubmit}>
        生成理解草案
      </button>
    </section>
  );
}
