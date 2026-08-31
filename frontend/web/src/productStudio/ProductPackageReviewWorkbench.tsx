import { useState, type FormEvent } from "react";
import { ProductStudioApiError } from "./api";
import {
  HttpProductPackageReviewApiClient,
  type ProductPackageReviewApiClient,
  type ProductPackageReviewInput,
  type ProductPackageReviewResponse,
} from "./productPackageReviewApi";

type ListField =
  | "market_insight_refs"
  | "competitor_evidence_refs"
  | "component_ids"
  | "skill_ids"
  | "success_metric_ids"
  | "guardrail_ids"
  | "stop_conditions"
  | "evidence_locators"
  | "assumptions"
  | "unknowns";

type FormState = Omit<ProductPackageReviewInput, ListField> & Record<ListField, string>;

type Props = {
  client?: ProductPackageReviewApiClient;
  initialInput?: ProductPackageReviewInput;
  contractPreview?: boolean;
};

const list = (values: string[]) => values.join("\n");
const parseList = (value: string) => [...new Set(value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean))];

function formFrom(input?: ProductPackageReviewInput): FormState {
  return {
    source_draft_locator: input?.source_draft_locator ?? "",
    concept_id: input?.concept_id ?? "",
    zone_assessment_id: input?.zone_assessment_id ?? "",
    product_kind: input?.product_kind ?? "MICRO_CAMP",
    duration_days: input?.duration_days ?? 21,
    primary_contradiction: input?.primary_contradiction ?? "",
    demand_ref: input?.demand_ref ?? "",
    market_insight_refs: list(input?.market_insight_refs ?? []),
    competitor_evidence_refs: list(input?.competitor_evidence_refs ?? []),
    component_ids: list(input?.component_ids ?? []),
    skill_ids: list(input?.skill_ids ?? []),
    success_metric_ids: list(input?.success_metric_ids ?? []),
    guardrail_ids: list(input?.guardrail_ids ?? []),
    stop_conditions: list(input?.stop_conditions ?? []),
    pause_policy: input?.pause_policy ?? "",
    human_gate_policy: input?.human_gate_policy ?? "",
    evidence_locators: list(input?.evidence_locators ?? []),
    assumptions: list(input?.assumptions ?? []),
    unknowns: list(input?.unknowns ?? []),
    next_validation: input?.next_validation ?? "",
    requested_ttl_hours: input?.requested_ttl_hours ?? 24,
  };
}

function toInput(form: FormState): ProductPackageReviewInput {
  const scalarValues = [
    form.source_draft_locator,
    form.concept_id,
    form.zone_assessment_id,
    form.primary_contradiction,
    form.demand_ref,
    form.pause_policy,
    form.human_gate_policy,
    form.next_validation,
  ];
  const lists = {
    market_insight_refs: parseList(form.market_insight_refs),
    competitor_evidence_refs: parseList(form.competitor_evidence_refs),
    component_ids: parseList(form.component_ids),
    skill_ids: parseList(form.skill_ids),
    success_metric_ids: parseList(form.success_metric_ids),
    guardrail_ids: parseList(form.guardrail_ids),
    stop_conditions: parseList(form.stop_conditions),
    evidence_locators: parseList(form.evidence_locators),
    assumptions: parseList(form.assumptions),
    unknowns: parseList(form.unknowns),
  };
  if (scalarValues.some((value) => !value.trim())
    || Object.values(lists).some((values) => values.length === 0)) {
    throw new ProductStudioApiError("INVALID_INPUT", "请完整填写设计依据、组件、证据凭证和验证边界。");
  }
  if (!Number.isInteger(form.duration_days) || form.duration_days < 1 || form.duration_days > 180) {
    throw new ProductStudioApiError("INVALID_INPUT", "产品周期必须是 1–180 天。");
  }
  if (!Number.isInteger(form.requested_ttl_hours)
    || form.requested_ttl_hours < 1
    || form.requested_ttl_hours > 168) {
    throw new ProductStudioApiError("INVALID_INPUT", "评审有效期必须是 1–168 小时。");
  }
  return {
    source_draft_locator: form.source_draft_locator.trim(),
    concept_id: form.concept_id.trim(),
    zone_assessment_id: form.zone_assessment_id.trim(),
    product_kind: form.product_kind,
    duration_days: form.duration_days,
    primary_contradiction: form.primary_contradiction.trim(),
    demand_ref: form.demand_ref.trim(),
    ...lists,
    pause_policy: form.pause_policy.trim(),
    human_gate_policy: form.human_gate_policy.trim(),
    next_validation: form.next_validation.trim(),
    requested_ttl_hours: form.requested_ttl_hours,
  };
}

function newIdempotencyKey(): string {
  const suffix = typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}`;
  return `product-package-review:${suffix}`;
}

export function ProductPackageReviewWorkbench({
  client = new HttpProductPackageReviewApiClient(),
  initialInput,
  contractPreview = false,
}: Props) {
  const [form, setForm] = useState(() => formFrom(initialInput));
  const [result, setResult] = useState<ProductPackageReviewResponse | null>(null);
  const [error, setError] = useState<ProductStudioApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [idempotencyKey, setIdempotencyKey] = useState<string | null>(null);

  const change = <K extends keyof FormState>(field: K, value: FormState[K]) => {
    setForm((current) => ({ ...current, [field]: value }));
    setResult(null);
    setError(null);
    setIdempotencyKey(null);
  };

  const execute = async () => {
    setError(null);
    let input: ProductPackageReviewInput;
    try {
      input = toInput(form);
    } catch (cause) {
      setError(cause as ProductStudioApiError);
      return;
    }
    const key = idempotencyKey ?? newIdempotencyKey();
    setIdempotencyKey(key);
    setBusy(true);
    try {
      setResult(await client.submit(input, key));
    } catch (cause) {
      setError(cause instanceof ProductStudioApiError
        ? cause
        : new ProductStudioApiError("INVALID_RESPONSE", "ProductPackage 评审返回异常。"));
    } finally {
      setBusy(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void execute();
  };

  const readBack = async () => {
    if (!result) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await client.get(result.draft.draft_id, result.draft.content_hash));
    } catch (cause) {
      setError(cause instanceof ProductStudioApiError
        ? new ProductStudioApiError(cause.code, `冻结快照回读失败；下方仍为上次已知快照。${cause.message}`, cause.httpStatus)
        : new ProductStudioApiError("INVALID_RESPONSE", "冻结快照回读失败。"));
    } finally {
      setBusy(false);
    }
  };

  const listField = (field: ListField, label: string, hint: string) => (
    <label>
      {label}
      <textarea
        rows={2}
        value={form[field]}
        onChange={(event) => change(field, event.target.value)}
        placeholder={hint}
      />
    </label>
  );

  return (
    <section aria-busy={busy} aria-label="ProductPackage Review Workbench" className="panel product-package-review-workbench">
      <div className="section-kicker">Market Evidence → ProductPackage v1.2 → Human Gate</div>
      <h2>产品包证据准入与评审</h2>
      <p className="muted">
        浏览器只提交设计意图和 receipt locator。三区结论、claim 范围、证据哈希、AI provenance 与人工任务均由服务端决定。
      </p>
      {contractPreview ? (
        <div className="callout" role="note">
          <strong>合同预览，尚未接入生产运行时</strong>
          <p>身份会话、正式路由挂载与 production source resolver 完成前，此入口只用于验证字段和评审结果呈现。</p>
        </div>
      ) : null}

      <form onSubmit={submit}>
        <fieldset disabled={busy || contractPreview}>
          <legend>1. 可信设计来源</legend>
          <div className="product-package-form-grid">
            <label>来源草案 locator<input value={form.source_draft_locator} onChange={(event) => change("source_draft_locator", event.target.value)} /></label>
            <label>产品概念 ID<input value={form.concept_id} onChange={(event) => change("concept_id", event.target.value)} /></label>
            <label>三区评估 ID<input value={form.zone_assessment_id} onChange={(event) => change("zone_assessment_id", event.target.value)} /></label>
            <label>需求引用<input value={form.demand_ref} onChange={(event) => change("demand_ref", event.target.value)} /></label>
            <label>
              产品形态
              <select value={form.product_kind} onChange={(event) => change("product_kind", event.target.value as FormState["product_kind"])}>
                <option value="MICRO_CAMP">21 天等最小试点 / MICRO_CAMP</option>
                <option value="SCALE_PLAN">扩展计划 / SCALE_PLAN</option>
                <option value="CUSTOM">自定义 / CUSTOM</option>
              </select>
            </label>
            <label>周期（天）<input min={1} max={180} type="number" value={form.duration_days} onChange={(event) => change("duration_days", Number(event.target.value))} /></label>
          </div>
          <label>家庭教育主矛盾<textarea rows={3} value={form.primary_contradiction} onChange={(event) => change("primary_contradiction", event.target.value)} /></label>
        </fieldset>

        <fieldset disabled={busy || contractPreview}>
          <legend>2. 市场证据、组件与 Skill</legend>
          <div className="product-package-form-grid">
            {listField("market_insight_refs", "市场洞察引用", "每行一个 insight:...")}
            {listField("competitor_evidence_refs", "竞品证据引用", "每行一个 competitor-evidence:...")}
            {listField("component_ids", "组件 ID", "每行一个 component:...")}
            {listField("skill_ids", "Skill ID", "每行一个 skill:...")}
            {listField("success_metric_ids", "成功指标 ID", "每行一个 metric:...")}
            {listField("guardrail_ids", "安全护栏 ID", "每行一个 guardrail:...")}
            {listField("stop_conditions", "停止条件", "每行一个 stop:...")}
            {listField("evidence_locators", "验证凭证 locator", "每行一个 verification-receipt:...")}
          </div>
        </fieldset>

        <fieldset disabled={busy || contractPreview}>
          <legend>3. 可暂停、可验证边界</legend>
          <div className="product-package-form-grid">
            {listField("assumptions", "待验证假设", "每行一个假设")}
            {listField("unknowns", "未知项", "每行一个未知项")}
          </div>
          <label>暂停策略<textarea rows={2} value={form.pause_policy} onChange={(event) => change("pause_policy", event.target.value)} /></label>
          <label>产品内人工介入规则（设计意图）<textarea rows={2} value={form.human_gate_policy} onChange={(event) => change("human_gate_policy", event.target.value)} /></label>
          <p className="muted">PDM Operator Gate 由服务端固定创建，此字段不能改变平台审批权限。</p>
          <label>下一步验证<textarea rows={2} value={form.next_validation} onChange={(event) => change("next_validation", event.target.value)} /></label>
          <label>评审有效期（小时）<input min={1} max={168} type="number" value={form.requested_ttl_hours} onChange={(event) => change("requested_ttl_hours", Number(event.target.value))} /></label>
          <button className="primary-button" type="submit">{busy ? "证据复核与提交中…" : "提交 ProductPackage 人工评审"}</button>
        </fieldset>
      </form>

      {error ? (
        <div className="callout" role="alert">
          <strong>{error.code}</strong><p>{error.message}</p>
          {error.code === "TIMEOUT" || error.code === "UNAVAILABLE" || error.code === "INVALID_RESPONSE" ? (
            <button className="secondary-button" onClick={() => void execute()} type="button">使用同一幂等键重试</button>
          ) : null}
        </div>
      ) : null}

      {result ? (
        <section aria-label="ProductPackage 评审提交结果" aria-live="polite" className="product-package-review-result" role="status">
          <div className="product-package-result-hero">
            <div>
              <span className="draft-badge">DRAFT · v{result.draft.version}</span>
              <h3>{result.draft.product_kind} · {result.draft.duration_days} 天</h3>
              <p>{result.draft.primary_contradiction}</p>
            </div>
            <div className="review-state">
              <span>{result.replayed ? "幂等重放" : "已提交评审"}</span>
              <strong>{result.review_task.status}</strong>
            </div>
          </div>

          <dl className="provenance-grid">
            <div><dt>已批准三区评估结果</dt><dd>{result.draft.approved_zone}</dd></div>
            <div><dt>Draft</dt><dd>{result.draft.draft_id}</dd></div>
            <div><dt>Human Task</dt><dd>{result.review_task.task_id}</dd></div>
            <div><dt>Risk</dt><dd>{result.review_task.risk_level}</dd></div>
            <div><dt>Content hash / ETag</dt><dd>{result.draft.content_hash} · {result.etag}</dd></div>
            <div><dt>有效期</dt><dd>{new Date(result.draft.expires_at).toLocaleString()}</dd></div>
          </dl>

          <h3>证据准入快照</h3>
          <div className="evidence-admission-grid">
            {result.draft.evidence_admissions.map((admission) => (
              <article key={admission.receipt_id}>
                <div><span className="draft-badge">{admission.admission_status}</span><strong>{admission.claim_type}</strong></div>
                <p><b>凭证：</b><code>{admission.receipt_id}</code></p>
                <p><b>证据：</b><code>{admission.evidence_id}</code> · v{admission.evidence_version}</p>
                <p><b>主张范围：</b>{admission.required_claim_refs.join("、")}</p>
                <p><b>适用边界：</b>{admission.required_applicability_refs.join("、")}</p>
                <p><b>验证方法：</b>{admission.verification_methods.join("、")}</p>
                <p><b>人工 lineage：</b>{admission.task_id} → {admission.decision_id}</p>
                <p><b>有效至：</b>{new Date(admission.valid_until).toLocaleString()}</p>
              </article>
            ))}
          </div>

          <div className="callout">
            <strong>这不是产品批准，也不是家庭成长事实</strong>
            <p>ADMITTED 只表示这些凭证可支持本次明确 claim 与适用范围；仍需人工 Gate，且不能外推到其他年龄、角色、场景或地区。</p>
          </div>
        </section>
      ) : null}
      {result ? (
        <button className="secondary-button" disabled={busy} onClick={() => void readBack()} type="button">回读服务端冻结快照</button>
      ) : null}
    </section>
  );
}
