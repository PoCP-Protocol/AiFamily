import { useRef, useState } from "react";
import {
  HttpProductStudioApiClient,
  ProductStudioApiError,
  type CompetitorEvidenceDraftResponse,
  type CompetitorEvidenceInput,
  type MarketInsightDraftResponse,
  type MarketInsightInput,
  type ProductDraftResponse,
  type ProductStudioApiClient,
} from "./api";

type EvidenceForm = {
  demandRef: string;
  competitorRef: string;
  claim: string;
  sourceRefs: string;
  sourceType: string;
  assumptions: string;
  unknowns: string;
  nextValidation: string;
  expiresAt: string;
  provenanceRef: string;
};

type InsightForm = {
  statement: string;
  sourceRefs: string;
  segmentRef: string;
  assumptions: string;
  unknowns: string;
  nextValidation: string;
  expiresAt: string;
  provenanceRef: string;
};

const defaultExpiry = "2099-01-01T00:00";

const initialEvidenceForm: EvidenceForm = {
  demandRef: "",
  competitorRef: "",
  claim: "",
  sourceRefs: "",
  sourceType: "official_webpage",
  assumptions: "",
  unknowns: "",
  nextValidation: "",
  expiresAt: defaultExpiry,
  provenanceRef: "",
};

const initialInsightForm: InsightForm = {
  statement: "",
  sourceRefs: "",
  segmentRef: "",
  assumptions: "",
  unknowns: "",
  nextValidation: "",
  expiresAt: defaultExpiry,
  provenanceRef: "",
};

const splitRefs = (value: string): string[] =>
  value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);

const toIsoExpiry = (value: string): string => {
  if (value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value)) return value;
  return `${value}:00+08:00`;
};

const newIdempotencyKey = (kind: string): string =>
  typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${kind}-${Date.now()}`;

function requireDraftFields(values: string[], assumptions: string[], unknowns: string[]): void {
  if (values.some((value) => !value.trim()) || assumptions.length === 0 || unknowns.length === 0) {
    throw new ProductStudioApiError(
      "INVALID_INPUT",
      "请完整填写需求引用、证据来源、假设、未知项、下一步验证和 provenance_ref。",
    );
  }
}

function toEvidenceInput(form: EvidenceForm): CompetitorEvidenceInput {
  const sourceRefs = splitRefs(form.sourceRefs);
  const assumptions = splitRefs(form.assumptions);
  const unknowns = splitRefs(form.unknowns);
  requireDraftFields(
    [
      form.demandRef,
      form.competitorRef,
      form.claim,
      form.sourceType,
      form.nextValidation,
      form.expiresAt,
      form.provenanceRef,
      ...sourceRefs,
    ],
    assumptions,
    unknowns,
  );
  return {
    competitor_ref: form.competitorRef.trim(),
    claim: form.claim.trim(),
    source_refs: sourceRefs,
    source_type: form.sourceType.trim(),
    evidence_status: "UNKNOWN",
    demand_ref: form.demandRef.trim(),
    evidence_refs: sourceRefs,
    assumptions,
    unknowns,
    next_validation: form.nextValidation.trim(),
    expires_at: toIsoExpiry(form.expiresAt),
    provenance_ref: form.provenanceRef.trim(),
  };
}

function toInsightInput(
  form: InsightForm,
  demandRef: string,
  evidenceId: string,
): MarketInsightInput {
  const sourceRefs = splitRefs(form.sourceRefs);
  const assumptions = splitRefs(form.assumptions);
  const unknowns = splitRefs(form.unknowns);
  requireDraftFields(
    [
      demandRef,
      evidenceId,
      form.statement,
      form.nextValidation,
      form.expiresAt,
      form.provenanceRef,
      ...sourceRefs,
    ],
    assumptions,
    unknowns,
  );
  return {
    demand_ref: demandRef,
    statement: form.statement.trim(),
    source_refs: sourceRefs,
    competitor_evidence_refs: [evidenceId],
    ...(form.segmentRef.trim() ? { segment_ref: form.segmentRef.trim() } : {}),
    evidence_refs: [...new Set([...sourceRefs, evidenceId])],
    assumptions,
    unknowns,
    next_validation: form.nextValidation.trim(),
    expires_at: toIsoExpiry(form.expiresAt),
    provenance_ref: form.provenanceRef.trim(),
  };
}

function ProvenanceSummary({ draft }: { draft: ProductDraftResponse }) {
  return (
    <dl className="provenance-grid">
      <div><dt>status</dt><dd>{draft.status}</dd></div>
      <div><dt>provenance</dt><dd>{draft.provenance_ref}</dd></div>
      {draft.expires_at ? <div><dt>expires</dt><dd>{draft.expires_at}</dd></div> : null}
      {draft.next_validation ? <div><dt>next validation</dt><dd>{draft.next_validation}</dd></div> : null}
      {draft.model_ref ? <div><dt>model</dt><dd>{String(draft.model_ref)}</dd></div> : null}
      {draft.prompt_use_case_version ? (
        <div><dt>prompt use case</dt><dd>{String(draft.prompt_use_case_version)}</dd></div>
      ) : null}
    </dl>
  );
}

type Props = { client?: ProductStudioApiClient };

export function MarketEvidenceWorkbench({ client = new HttpProductStudioApiClient() }: Props) {
  const [evidenceForm, setEvidenceForm] = useState<EvidenceForm>(initialEvidenceForm);
  const [insightForm, setInsightForm] = useState<InsightForm>(initialInsightForm);
  const [evidence, setEvidence] = useState<CompetitorEvidenceDraftResponse | null>(null);
  const [insight, setInsight] = useState<MarketInsightDraftResponse | null>(null);
  const [error, setError] = useState<ProductStudioApiError | null>(null);
  const [submitting, setSubmitting] = useState<"evidence" | "insight" | null>(null);
  const evidenceKey = useRef<string | undefined>(undefined);
  const insightKey = useRef<string | undefined>(undefined);

  const updateEvidence = (field: keyof EvidenceForm, value: string) => {
    evidenceKey.current = undefined;
    insightKey.current = undefined;
    setEvidence(null);
    setInsight(null);
    setEvidenceForm((current) => ({ ...current, [field]: value }));
  };

  const updateInsight = (field: keyof InsightForm, value: string) => {
    insightKey.current = undefined;
    setInsight(null);
    setInsightForm((current) => ({ ...current, [field]: value }));
  };

  const submitEvidence = async () => {
    setError(null);
    if (!client.getCompetitorEvidence) {
      setError(new ProductStudioApiError("UNAVAILABLE", "当前客户端不支持竞品证据回读。"));
      return;
    }
    let input: CompetitorEvidenceInput;
    try {
      input = toEvidenceInput(evidenceForm);
    } catch (cause) {
      setError(cause instanceof ProductStudioApiError ? cause : new ProductStudioApiError("INVALID_INPUT", "竞品证据输入不完整。"));
      return;
    }
    const key = evidenceKey.current ?? newIdempotencyKey("competitor-evidence");
    evidenceKey.current = key;
    setSubmitting("evidence");
    try {
      const created = await client.createCompetitorEvidence(input, key);
      const persisted = await client.getCompetitorEvidence(created.evidence_id);
      if (persisted.evidence_id !== created.evidence_id) {
        throw new ProductStudioApiError("INVALID_RESPONSE", "竞品证据回读 ID 与创建结果不一致。");
      }
      setEvidence(persisted);
    } catch (cause) {
      setError(cause instanceof ProductStudioApiError ? cause : new ProductStudioApiError("INVALID_RESPONSE", "竞品证据创建或回读失败。"));
    } finally {
      setSubmitting(null);
    }
  };

  const submitInsight = async () => {
    setError(null);
    if (!evidence) {
      setError(new ProductStudioApiError("INVALID_INPUT", "请先创建并回读竞品证据。"));
      return;
    }
    let input: MarketInsightInput;
    try {
      input = toInsightInput(insightForm, evidenceForm.demandRef.trim(), evidence.evidence_id);
    } catch (cause) {
      setError(cause instanceof ProductStudioApiError ? cause : new ProductStudioApiError("INVALID_INPUT", "市场洞察输入不完整。"));
      return;
    }
    const key = insightKey.current ?? newIdempotencyKey("market-insight");
    insightKey.current = key;
    setSubmitting("insight");
    try {
      setInsight(await client.createMarketInsight(input, key));
    } catch (cause) {
      setError(cause instanceof ProductStudioApiError ? cause : new ProductStudioApiError("INVALID_RESPONSE", "市场洞察草案创建失败。"));
    } finally {
      setSubmitting(null);
    }
  };

  const gateBlocked = evidence?.evidence_status !== "VERIFIED";

  return (
    <section aria-label="Market Evidence Workbench" className="panel market-evidence-workbench">
      <div className="section-kicker">IPD · Market &amp; Competitor Evidence</div>
      <h2>市场与竞品证据工作台</h2>
      <p className="muted">先创建证据卡并从服务端回读，再生成引用该证据的市场洞察。全程仅为 DRAFT。</p>

      <fieldset disabled={submitting !== null}>
        <legend>1. 竞品证据卡</legend>
        <label className="field-label" htmlFor="evidence-demand-ref">需求引用</label>
        <input id="evidence-demand-ref" value={evidenceForm.demandRef} onChange={(event) => updateEvidence("demandRef", event.target.value)} placeholder="demand:..." />
        <label className="field-label" htmlFor="evidence-competitor-ref">竞品引用</label>
        <input id="evidence-competitor-ref" value={evidenceForm.competitorRef} onChange={(event) => updateEvidence("competitorRef", event.target.value)} />
        <label className="field-label" htmlFor="evidence-claim">可核查主张</label>
        <textarea id="evidence-claim" rows={2} value={evidenceForm.claim} onChange={(event) => updateEvidence("claim", event.target.value)} />
        <label className="field-label" htmlFor="evidence-source-refs">证据来源（逗号或换行分隔）</label>
        <input id="evidence-source-refs" value={evidenceForm.sourceRefs} onChange={(event) => updateEvidence("sourceRefs", event.target.value)} placeholder="https://..." />
        <label className="field-label" htmlFor="evidence-source-type">来源类型</label>
        <input id="evidence-source-type" value={evidenceForm.sourceType} onChange={(event) => updateEvidence("sourceType", event.target.value)} />
        <label className="field-label" htmlFor="evidence-assumptions">证据假设（逗号或换行分隔）</label>
        <textarea id="evidence-assumptions" rows={2} value={evidenceForm.assumptions} onChange={(event) => updateEvidence("assumptions", event.target.value)} />
        <label className="field-label" htmlFor="evidence-unknowns">证据未知项（逗号或换行分隔）</label>
        <textarea id="evidence-unknowns" rows={2} value={evidenceForm.unknowns} onChange={(event) => updateEvidence("unknowns", event.target.value)} />
        <label className="field-label" htmlFor="evidence-next-validation">证据下一步验证</label>
        <textarea id="evidence-next-validation" rows={2} value={evidenceForm.nextValidation} onChange={(event) => updateEvidence("nextValidation", event.target.value)} />
        <label className="field-label" htmlFor="evidence-expires">证据有效期</label>
        <input id="evidence-expires" type="datetime-local" value={evidenceForm.expiresAt} onChange={(event) => updateEvidence("expiresAt", event.target.value)} />
        <label className="field-label" htmlFor="evidence-provenance">证据 provenance_ref</label>
        <input id="evidence-provenance" value={evidenceForm.provenanceRef} onChange={(event) => updateEvidence("provenanceRef", event.target.value)} />
        <p className="muted">新证据固定以 UNKNOWN 创建；工作台不提供自我标记 VERIFIED 的捷径。</p>
        <button className="primary-button" type="button" onClick={() => void submitEvidence()}>
          {submitting === "evidence" ? "创建并回读中…" : "创建并回读竞品证据"}
        </button>
      </fieldset>

      {evidence ? (
        <output aria-label="已回读竞品证据" className="callout">
          <strong>DRAFT · {evidence.evidence_status}</strong>
          <p><code>{evidence.evidence_id}</code></p>
          <p>{evidence.claim}</p>
          <ProvenanceSummary draft={evidence} />
          <p role="status">{gateBlocked ? "证据尚未 VERIFIED，不可进入 Gate。" : "证据已 VERIFIED，仍需人工 Gate 审查。"}</p>
        </output>
      ) : null}

      <fieldset disabled={!evidence || submitting !== null}>
        <legend>2. 市场洞察草案</legend>
        <p className="muted">竞品证据引用：{evidence?.evidence_id ?? "等待证据回读"}</p>
        <label className="field-label" htmlFor="insight-statement">市场洞察陈述</label>
        <textarea id="insight-statement" rows={3} value={insightForm.statement} onChange={(event) => updateInsight("statement", event.target.value)} />
        <label className="field-label" htmlFor="insight-source-refs">洞察来源（逗号或换行分隔）</label>
        <input id="insight-source-refs" value={insightForm.sourceRefs} onChange={(event) => updateInsight("sourceRefs", event.target.value)} />
        <label className="field-label" htmlFor="insight-segment-ref">分群引用（可选）</label>
        <input id="insight-segment-ref" value={insightForm.segmentRef} onChange={(event) => updateInsight("segmentRef", event.target.value)} />
        <label className="field-label" htmlFor="insight-assumptions">洞察假设（逗号或换行分隔）</label>
        <textarea id="insight-assumptions" rows={2} value={insightForm.assumptions} onChange={(event) => updateInsight("assumptions", event.target.value)} />
        <label className="field-label" htmlFor="insight-unknowns">洞察未知项（逗号或换行分隔）</label>
        <textarea id="insight-unknowns" rows={2} value={insightForm.unknowns} onChange={(event) => updateInsight("unknowns", event.target.value)} />
        <label className="field-label" htmlFor="insight-next-validation">洞察下一步验证</label>
        <textarea id="insight-next-validation" rows={2} value={insightForm.nextValidation} onChange={(event) => updateInsight("nextValidation", event.target.value)} />
        <label className="field-label" htmlFor="insight-expires">洞察有效期</label>
        <input id="insight-expires" type="datetime-local" value={insightForm.expiresAt} onChange={(event) => updateInsight("expiresAt", event.target.value)} />
        <label className="field-label" htmlFor="insight-provenance">洞察 provenance_ref</label>
        <input id="insight-provenance" value={insightForm.provenanceRef} onChange={(event) => updateInsight("provenanceRef", event.target.value)} />
        <button className="primary-button" type="button" onClick={() => void submitInsight()}>
          {submitting === "insight" ? "提交中…" : "创建市场洞察草案"}
        </button>
      </fieldset>

      {insight ? (
        <output aria-label="市场洞察草案结果" className="callout">
          <strong>DRAFT</strong>
          <p>{insight.statement}</p>
          <p>引用竞品证据：<code>{insight.competitor_evidence_refs.join(", ")}</code></p>
          <ProvenanceSummary draft={insight} />
          <p role="status">{gateBlocked ? "关联证据尚未 VERIFIED，不可进入 Gate。" : "仍需人工 Gate 审查；不会自动推进。"}</p>
        </output>
      ) : null}

      {error ? <p role="alert">错误：{error.code} · {error.message}</p> : null}
    </section>
  );
}
