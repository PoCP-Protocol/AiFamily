import { useRef, useState } from "react";
import {
  HttpProductStudioApiClient,
  ProductStudioApiError,
  type DemandFrameInput,
  type ProductDraftResponse,
  type ProductStudioApiClient,
} from "./api";

type ComposerForm = {
  statement: string;
  scenario: string;
  sourceRefs: string;
  targetSegment: string;
  expiresAt: string;
  assumptions: string;
  unknowns: string;
  nextValidation: string;
  provenanceRef: string;
};

const initialForm: ComposerForm = {
  statement: "",
  scenario: "",
  sourceRefs: "",
  targetSegment: "",
  expiresAt: "2099-01-01T00:00",
  assumptions: "",
  unknowns: "",
  nextValidation: "",
  provenanceRef: "",
};

type Props = {
  client?: ProductStudioApiClient;
};

const splitRefs = (value: string): string[] => value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);

const toIsoExpiry = (value: string): string => {
  if (value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value)) return value;
  return `${value}:00+08:00`;
};

const newIdempotencyKey = (): string =>
  typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `product-draft-${Date.now()}`;

function toDemandInput(form: ComposerForm): DemandFrameInput {
  const sourceRefs = splitRefs(form.sourceRefs);
  const required = [
    form.statement,
    form.scenario,
    form.targetSegment,
    form.nextValidation,
    form.provenanceRef,
    ...sourceRefs,
  ];
  if (required.some((item) => !item.trim())) {
    throw new ProductStudioApiError("INVALID_INPUT", "请完整填写需求、来源、假设验证与 provenance_ref。");
  }
  return {
    statement: form.statement.trim(),
    scenario: form.scenario.trim(),
    source_refs: sourceRefs,
    target_segment: form.targetSegment.trim(),
    locale: "zh-CN",
    purpose: "product_discovery",
    evidence_refs: sourceRefs,
    assumptions: splitRefs(form.assumptions),
    unknowns: splitRefs(form.unknowns),
    next_validation: form.nextValidation.trim(),
    expires_at: toIsoExpiry(form.expiresAt),
    provenance_ref: form.provenanceRef.trim(),
  };
}

export function ProductFactoryComposer({ client = new HttpProductStudioApiClient() }: Props) {
  const [form, setForm] = useState<ComposerForm>(initialForm);
  const [draft, setDraft] = useState<ProductDraftResponse | null>(null);
  const [error, setError] = useState<ProductStudioApiError | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const idempotencyKey = useRef<string | undefined>(undefined);

  const update = (field: keyof ComposerForm, value: string) => setForm((current) => ({ ...current, [field]: value }));

  const submit = async () => {
    setError(null);
    setDraft(null);
    let input: DemandFrameInput;
    try {
      input = toDemandInput(form);
    } catch (cause) {
      setError(cause instanceof ProductStudioApiError ? cause : new ProductStudioApiError("INVALID_INPUT", "输入不完整。"));
      return;
    }
    const key = idempotencyKey.current ?? newIdempotencyKey();
    idempotencyKey.current = key;
    setSubmitting(true);
    try {
      const result = await client.createDemandFrame(input, key);
      setDraft(result);
    } catch (cause) {
      setError(cause instanceof ProductStudioApiError ? cause : new ProductStudioApiError("INVALID_INPUT", "需求草案提交失败。"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section aria-label="Product Factory Composer" className="panel product-factory-composer">
      <div className="section-kicker">IPD · Demand Studio</div>
      <h2>创建需求草案</h2>
      <p className="muted">这是产品设计输入，不是家庭事实。提交后仅显示 DRAFT 和可追溯 provenance。</p>

      <label className="field-label" htmlFor="product-statement">需求陈述</label>
      <textarea id="product-statement" value={form.statement} onChange={(event) => update("statement", event.target.value)} rows={3} />
      <label className="field-label" htmlFor="product-scenario">场景</label>
      <input id="product-scenario" value={form.scenario} onChange={(event) => update("scenario", event.target.value)} />
      <label className="field-label" htmlFor="product-source-refs">来源引用（逗号或换行分隔）</label>
      <input id="product-source-refs" value={form.sourceRefs} onChange={(event) => update("sourceRefs", event.target.value)} placeholder="voc:001, research:002" />
      <label className="field-label" htmlFor="product-segment">目标分群</label>
      <input id="product-segment" value={form.targetSegment} onChange={(event) => update("targetSegment", event.target.value)} />
      <label className="field-label" htmlFor="product-expires">草案有效期</label>
      <input id="product-expires" type="datetime-local" value={form.expiresAt} onChange={(event) => update("expiresAt", event.target.value)} />
      <label className="field-label" htmlFor="product-assumptions">假设（逗号或换行分隔）</label>
      <textarea id="product-assumptions" value={form.assumptions} onChange={(event) => update("assumptions", event.target.value)} rows={2} />
      <label className="field-label" htmlFor="product-unknowns">未知项（逗号或换行分隔）</label>
      <textarea id="product-unknowns" value={form.unknowns} onChange={(event) => update("unknowns", event.target.value)} rows={2} />
      <label className="field-label" htmlFor="product-next-validation">下一步验证</label>
      <textarea id="product-next-validation" value={form.nextValidation} onChange={(event) => update("nextValidation", event.target.value)} rows={2} />
      <label className="field-label" htmlFor="product-provenance">provenance_ref</label>
      <input id="product-provenance" value={form.provenanceRef} onChange={(event) => update("provenanceRef", event.target.value)} placeholder="model-draft:..." />

      <button className="primary-button" type="button" disabled={submitting} onClick={() => void submit()}>
        {submitting ? "提交中…" : "提交需求草案"}
      </button>
      <p className="muted">幂等键：{idempotencyKey.current ?? "提交时生成"}</p>

      {error ? <p role="alert">错误：{error.code} · {error.message}</p> : null}
      {draft ? (
        <output aria-label="需求草案结果" className="callout">
          <strong>DRAFT</strong>
          <p>需求草案已生成，仍需人工审查，不能作为已验证市场事实。</p>
          <code>provenance_ref: {draft.provenance_ref}</code>
        </output>
      ) : null}
    </section>
  );
}
