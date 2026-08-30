import { useState } from "react";
import type { CreateDraftInput } from "../api/client";

export type ExpressionForm = Pick<CreateDraftInput, "payload" | "media_inputs" | "scope">;

type Props = {
  value: ExpressionForm;
  disabled: boolean;
  mode?: "expression" | "assessment";
  onChange: (value: ExpressionForm) => void;
  onSubmit: () => void;
  onCancel?: () => void;
};

export function ExpressionInput({ value, disabled, mode = "expression", onChange, onSubmit, onCancel }: Props) {
  const image = value.media_inputs[0];
  const [imageDraft, setImageDraft] = useState(image?.uri ?? "");
  const [imageConfirmed, setImageConfirmed] = useState(Boolean(image));

  const confirmImage = () => {
    if (!imageDraft.trim()) return;
    setImageConfirmed(true);
    onChange({
      ...value,
      media_inputs: [{ media_type: "IMAGE", uri: imageDraft.trim(), mime_type: "image/*", sha256: "web-reference" }],
    });
  };

  const clearImage = () => {
    setImageDraft("");
    setImageConfirmed(false);
    onChange({ ...value, media_inputs: [] });
  };

  return (
    <section className="panel" aria-labelledby="expression-heading">
      <div className="journey-stepper" aria-label="家庭支持步骤">
        <span className="journey-step-active">1 说一件小事</span>
        <span>2 看见重点</span>
        <span>3 试一小步</span>
      </div>
      <h2 id="expression-heading">
        {mode === "assessment" ? "从一件小事开始看看" : "你最近最想先解决哪件小事？"}
      </h2>
      <p className="muted">
        {mode === "assessment"
          ? "选一个最想先看看方向，再补充具体发生了什么。没有标准答案。"
          : "写下真实发生的片段就好，我们会先帮你整理重点。"
        }
      </p>
      {mode === "assessment" ? (
        <div className="choice-grid" aria-label="想先看看哪件小事">
          {["沟通总是绕回争吵", "写作业和生活习惯", "手机和屏幕时间", "我还说不清楚"].map((choice) => (
            <button
              className={`choice-button${value.payload.expression.startsWith(choice) ? " choice-button-selected" : ""}`}
              type="button"
              key={choice}
              disabled={disabled}
              onClick={() => onChange({ ...value, payload: { expression: `${choice}。` } })}
            >
              {choice}
            </button>
          ))}
        </div>
      ) : null}
      <label className="field-label" htmlFor="expression">
        {mode === "assessment" ? "补充一件最近发生的事（可选）" : "写给自己的话"}
      </label>
      <textarea
        id="expression"
        value={value.payload.expression}
        disabled={disabled}
        onChange={(event) =>
          onChange({ ...value, payload: { expression: event.target.value } })
        }
        placeholder="例如：昨天又因为写作业催了很久，后来谁都不想说话……"
        rows={mode === "assessment" ? 4 : 6}
      />
      <label className="field-label" htmlFor="image-reference">
        加一张图片（可选）
      </label>
      <input
        id="image-reference"
        value={imageDraft}
        disabled={disabled}
        onChange={(event) => {
          setImageDraft(event.target.value);
          setImageConfirmed(false);
        }}
        placeholder="粘贴图片链接，先预览再确认"
      />
      {imageDraft ? (
        <div className="media-preview" aria-label="图片预览">
          <div className="media-preview-art" role="img" aria-label="已选择的图片预览">图片</div>
          <div>
            <strong>{imageConfirmed ? "图片已确认" : "请确认这张图片"}</strong>
            <p className="muted">它只作为这次表达的线索。</p>
          </div>
          <div className="media-preview-actions">
            <button className="secondary-button" type="button" disabled={disabled || imageConfirmed} onClick={confirmImage}>
              {imageConfirmed ? "已确认" : "确认使用"}
            </button>
            <button className="text-button" type="button" disabled={disabled} onClick={clearImage}>取消</button>
          </div>
        </div>
      ) : null}
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
        <span>我同意本次只为整理这段表达而使用我主动提供的内容。</span>
      </label>
      <div className="form-actions">
        {onCancel ? <button className="text-button" type="button" disabled={disabled} onClick={onCancel}>先回首页</button> : null}
        <button className="primary-button" type="button" disabled={disabled} onClick={onSubmit}>
          看看我们听到了什么
        </button>
      </div>
    </section>
  );
}
