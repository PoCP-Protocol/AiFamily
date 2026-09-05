import { useRef, useState } from "react";
import {
  DecisionApiError,
  HttpProductDecisionApiClient,
  ZONE_DIMENSIONS,
  type CandidateReference,
  type ProductConceptCandidate,
  type ProductDecisionApiClient,
  type RecommendedZone,
  type ZoneDimension,
} from "./decisionApi";
import { OpportunityLineagePanel } from "./OpportunityLineagePanel";
import { deriveEvidenceCoverage, type EvidenceCoverage } from "./evidenceCoverage";

const ZONE_LABELS: Record<RecommendedZone, string> = {
  COMMODITY: "同质区",
  ADVANTAGE: "优势区",
  UNIQUE: "独特区",
};

const DIMENSION_LABELS: Record<ZoneDimension, string> = {
  customer_scarcity: "客户稀缺性",
  replaceability: "可替代性",
  data_advantage: "数据优势",
  network_effect: "网络效应",
  learning_effect: "学习效应",
  switching_cost: "转换成本",
};

export type CandidateDecisionDraft = {
  draft_id: string;
  status: "DRAFT";
  action: "PROPOSE_CANDIDATE_SELECTION" | "RETURN_TO_RESEARCH";
  concept_id: string;
  concept_version: number;
  assessment_id: string;
  assessment_version: number;
  opportunity_id: string | null;
  opportunity_version: number | null;
  zone_policy_version_id: string;
  recommended_zone: RecommendedZone;
  approved_zone: RecommendedZone | null;
  candidate_set_refs: string[];
  research_context: (EvidenceCoverage & { derived_from_chain_versions: string[] }) | null;
  reason: string;
  persisted: false;
  created_at: string;
};

type PendingAction = CandidateDecisionDraft["action"];
type Props = {
  client?: ProductDecisionApiClient;
  contractPreview?: boolean;
  onDecisionDraft?: (draft: CandidateDecisionDraft) => void;
};

const emptyReference = (): CandidateReference => ({ conceptId: "", assessmentId: "" });

function newDraftId(): string {
  return typeof crypto.randomUUID === "function"
    ? `decision-draft:${crypto.randomUUID()}`
    : `decision-draft:${Date.now()}`;
}

export function ProductConceptDecisionWorkbench({
  client = new HttpProductDecisionApiClient(),
  contractPreview = false,
  onDecisionDraft,
}: Props) {
  const [references, setReferences] = useState<CandidateReference[]>([emptyReference(), emptyReference()]);
  const [candidates, setCandidates] = useState<ProductConceptCandidate[]>([]);
  const [selectedConceptId, setSelectedConceptId] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [pendingAction, setPendingAction] = useState<PendingAction | null>(null);
  const [decisionDraft, setDecisionDraft] = useState<CandidateDecisionDraft | null>(null);
  const [error, setError] = useState<DecisionApiError | null>(null);
  const [loading, setLoading] = useState(false);
  const [researchFlowNotice, setResearchFlowNotice] = useState<string | null>(null);
  const [researchContext, setResearchContext] = useState<EvidenceCoverage | null>(null);
  const reasonRef = useRef<HTMLTextAreaElement>(null);

  const resetDecision = () => {
    setSelectedConceptId(null);
    setReason("");
    setPendingAction(null);
    setDecisionDraft(null);
    setResearchFlowNotice(null);
    setResearchContext(null);
  };

  const updateReference = (index: number, field: keyof CandidateReference, value: string) => {
    setReferences((current) => current.map((reference, candidateIndex) => (
      candidateIndex === index ? { ...reference, [field]: value } : reference
    )));
    setCandidates([]);
    setError(null);
    resetDecision();
  };

  const addReference = () => {
    if (references.length >= 5) return;
    setReferences((current) => [...current, emptyReference()]);
    setCandidates([]);
    resetDecision();
  };

  const removeReference = (index: number) => {
    if (references.length <= 2) return;
    setReferences((current) => current.filter((_, candidateIndex) => candidateIndex !== index));
    setCandidates([]);
    resetDecision();
  };

  const load = async () => {
    setError(null);
    setCandidates([]);
    resetDecision();
    setLoading(true);
    try {
      setCandidates(await client.loadCandidates(references));
    } catch (cause) {
      setError(cause instanceof DecisionApiError
        ? cause
        : new DecisionApiError("INVALID_RESPONSE", "产品候选读取失败。"));
    } finally {
      setLoading(false);
    }
  };

  const selected = candidates.find(({ concept }) => concept.id === selectedConceptId) ?? null;
  const selectionAllowed = selected !== null
    && selected.lineage.opportunity !== null
    && selected.concept.status !== "RETIRED"
    && !["REJECTED", "RETIRED"].includes(selected.assessment.status);
  const canPrepare = selected !== null && reason.trim().length > 0;

  const selectCandidateSafely = (
    conceptId: string,
    coverage: EvidenceCoverage | null = null,
    focusReason = false,
  ) => {
    if (conceptId === selectedConceptId) {
      if (coverage) setResearchContext(coverage);
      if (focusReason) reasonRef.current?.focus();
      return;
    }
    if (pendingAction || decisionDraft) {
      setResearchFlowNotice("已有待确认动作或决策草案；请先完成当前流程，再切换候选。");
      if (focusReason) reasonRef.current?.focus();
      return;
    }
    setSelectedConceptId(conceptId);
    setReason("");
    setPendingAction(null);
    setDecisionDraft(null);
    setResearchFlowNotice(null);
    setResearchContext(coverage);
    if (focusReason) reasonRef.current?.focus();
  };

  const beginReturnToResearch = (conceptId: string, coverage: EvidenceCoverage) => {
    selectCandidateSafely(conceptId, coverage, true);
  };

  const prepare = (action: PendingAction) => {
    if (!canPrepare || (action === "PROPOSE_CANDIDATE_SELECTION" && !selectionAllowed)) return;
    setPendingAction(action);
    setDecisionDraft(null);
  };

  const confirm = () => {
    if (!selected || !pendingAction || !reason.trim()) return;
    const coverage = researchContext ?? deriveEvidenceCoverage(selected.lineage);
    const draft: CandidateDecisionDraft = {
      draft_id: newDraftId(),
      status: "DRAFT",
      action: pendingAction,
      concept_id: selected.concept.id,
      concept_version: selected.concept.version,
      assessment_id: selected.assessment.id,
      assessment_version: selected.assessment.version,
      opportunity_id: selected.lineage.opportunity?.id ?? null,
      opportunity_version: selected.lineage.opportunity?.version ?? null,
      zone_policy_version_id: selected.assessment.zone_policy_version_id,
      recommended_zone: selected.assessment.recommended_zone,
      approved_zone: selected.assessment.approved_zone,
      candidate_set_refs: candidates.map(({ concept, assessment }) => `${concept.id}@v${concept.version}|${assessment.id}@v${assessment.version}|${assessment.zone_policy_version_id}`),
      research_context: pendingAction === "RETURN_TO_RESEARCH" ? {
        ...coverage,
        derived_from_chain_versions: [
          selected.lineage.market_signal,
          selected.lineage.customer_insight,
          selected.lineage.opportunity,
        ].filter((record) => record !== null).map((record) => `${record.id}@v${record.version}`),
      } : null,
      reason: reason.trim(),
      persisted: false,
      created_at: new Date().toISOString(),
    };
    setDecisionDraft(draft);
    setPendingAction(null);
    onDecisionDraft?.(draft);
  };

  return (
    <section aria-label="Product Concept Decision Workbench" className="panel product-concept-decision-workbench">
      <div className="section-kicker">IPD · Product Concept · Three-Zone Review</div>
      <h2>产品概念候选决策台</h2>
      <p className="muted">比较同一 Opportunity 下的多个候选、六维规则评估与证据引用。规则推荐不是事实或人工批准，界面不会排序或自动选择赢家。</p>

      {contractPreview ? (
        <div className="callout" role="note">
          <strong>合同预览，Concept chain 与三区路由尚未生产挂载</strong>
          <p>生产身份、路由和权威 Opportunity 决策对象接通前，不发网络请求，也不加载候选 fixture。</p>
        </div>
      ) : null}

      <fieldset disabled={loading || contractPreview}>
        <legend>候选引用（2–5 个）</legend>
        {references.map((reference, index) => (
          <div className="candidate-reference-row" key={`candidate-reference-${index + 1}`}>
            <label>
              候选 {index + 1} concept_id
              <input value={reference.conceptId} onChange={(event) => updateReference(index, "conceptId", event.target.value)} />
            </label>
            <label>
              候选 {index + 1} assessment_id
              <input value={reference.assessmentId} onChange={(event) => updateReference(index, "assessmentId", event.target.value)} />
            </label>
            {references.length > 2 ? (
              <button type="button" className="text-button" onClick={() => removeReference(index)}>
                移除候选 {index + 1}
              </button>
            ) : null}
          </div>
        ))}
        <div className="result-actions">
          <button type="button" className="secondary-button" disabled={references.length >= 5} onClick={addReference}>增加候选</button>
          <button type="button" className="primary-button" onClick={() => void load()}>{loading ? "读取中…" : "读取候选与三区证据"}</button>
        </div>
      </fieldset>

      {error ? <p role="alert">错误：{error.code} · {error.message}</p> : null}

      {candidates.length > 0 ? (
        <div aria-label="产品概念候选列表" className="product-candidate-grid">
          {candidates.map(({ concept, assessment, lineage }, index) => (
            <article className="candidate-card" data-candidate-order={index + 1} key={concept.id}>
              <label className="candidate-choice">
                <input
                  type="radio"
                  name="product-concept-candidate"
                  checked={selectedConceptId === concept.id}
                  onChange={() => selectCandidateSafely(concept.id)}
                />
                人工选择候选 {index + 1}
              </label>
              <h3>{concept.title}</h3>
              <p>{concept.description ?? "暂无描述"}</p>
              <code>{concept.id}</code>

              <OpportunityLineagePanel
                conceptTitle={concept.title}
                conceptRef={concept.id}
                lineage={lineage}
                onReturnToResearch={(coverage) => beginReturnToResearch(concept.id, coverage)}
              />

              <div className="zone-decision-columns">
                <div>
                  <span>RULE_RECOMMENDATION</span>
                  <strong>{ZONE_LABELS[assessment.recommended_zone]}</strong>
                  <small>{assessment.recommended_zone} · 非批准</small>
                </div>
                <div>
                  <span>人工评审快照</span>
                  <strong>{assessment.approved_zone ? ZONE_LABELS[assessment.approved_zone] : "待人工治理"}</strong>
                  <small>{assessment.approved_zone ?? "approved_zone 未设置"}</small>
                </div>
              </div>

              <p className="muted">RULE_ASSESSMENT · 评估状态：{assessment.status} · 差异化指数 {assessment.differentiation_index} · 防御性指数 {assessment.defensibility_index}</p>
              <p className="muted">策略版本：<code>{assessment.zone_policy_version_id}</code></p>
              {assessment.reviewed_by ? (
                <p className="muted">
                  人工评审：{assessment.reviewed_by} · {assessment.reviewed_at} · {assessment.review_reason}
                  {assessment.override_reason ? ` · 覆盖原因：${assessment.override_reason}` : ""}
                </p>
              ) : null}
              <ol aria-label={`${concept.title} 六维规则评估与 FACT_REF`} className="zone-evidence-list">
                {ZONE_DIMENSIONS.map((dimensionName) => {
                  const dimension = assessment.dimension_assessments.find(({ dimension }) => dimension === dimensionName)!;
                  return (
                    <li key={dimensionName}>
                      <strong>RULE_ASSESSMENT · {DIMENSION_LABELS[dimensionName]} · {dimension.score}</strong>
                      <span>规则理由：{dimension.rationale}</span>
                      <small>RULE_METADATA · evidence_strength {dimension.evidence_strength}</small>
                      <small>FACT_REF · {dimension.evidence_refs.join(", ")}</small>
                    </li>
                  );
                })}
              </ol>
              {selectedConceptId === concept.id && !selectionAllowed ? (
                <p role="status">
                  {lineage.opportunity === null
                    ? "UPSTREAM_OPPORTUNITY_NOT_RETURNED：上游机会未返回，仅可退回研究。"
                    : "ASSESSMENT_OR_CONCEPT_TERMINAL：概念或评估已终止，仅可退回研究。"}
                </p>
              ) : null}
            </article>
          ))}
        </div>
      ) : null}

      {candidates.length > 0 ? (
        <section aria-label="人工候选决策" className="candidate-human-decision">
          <h3>人工决策理由</h3>
          {researchContext ? (
            <p className="muted" aria-label="带入的研究缺口">
              客户端派生研究上下文：验证 {researchContext.verification}；节点缺口 {researchContext.nodes
                .filter(({ reason_code }) => reason_code)
                .map(({ reason_code }) => reason_code)
                .join("；") || "无结构缺口"}
            </p>
          ) : null}
          <textarea
            ref={reasonRef}
            aria-label="人工决策理由"
            rows={3}
            value={reason}
            onChange={(event) => {
              setReason(event.target.value);
              setPendingAction(null);
              setDecisionDraft(null);
            }}
            placeholder="说明为什么选择，或需要补充哪些研究证据"
          />
          <div className="result-actions">
            <button type="button" className="primary-button" disabled={!canPrepare || !selectionAllowed} onClick={() => prepare("PROPOSE_CANDIDATE_SELECTION")}>准备提议选择候选</button>
            <button type="button" className="secondary-button" disabled={!canPrepare} onClick={() => prepare("RETURN_TO_RESEARCH")}>准备退回研究</button>
          </div>
        </section>
      ) : null}

      {researchFlowNotice ? <p role="status">{researchFlowNotice}</p> : null}

      {pendingAction && selected ? (
        <section aria-label="确认人工决策" className="callout">
          <strong>确认生成 DRAFT</strong>
          <p>
            {pendingAction === "PROPOSE_CANDIDATE_SELECTION" ? "提议选择候选" : "退回研究"}：{selected.concept.title}
          </p>
          <p>此操作不会调用 approve/reject，也不会持久化或推进 Gate。</p>
          <button type="button" className="human-button" onClick={confirm}>
            {pendingAction === "PROPOSE_CANDIDATE_SELECTION" ? "确认生成提议选择草案" : "确认生成退回研究草案"}
          </button>
        </section>
      ) : null}

      {decisionDraft ? (
        <output aria-label="候选决策草案" className="callout">
          <strong>DRAFT · {decisionDraft.action}</strong>
          <p><code>{decisionDraft.concept_id}</code></p>
          <p>{decisionDraft.reason}</p>
          <p>冻结版本：Concept v{decisionDraft.concept_version} · Assessment v{decisionDraft.assessment_version} · Opportunity {decisionDraft.opportunity_id ?? "MISSING"}@v{decisionDraft.opportunity_version ?? "MISSING"}</p>
          <p>三区策略：<code>{decisionDraft.zone_policy_version_id}</code> · 候选集合：{decisionDraft.candidate_set_refs.join("；")}</p>
          {decisionDraft.research_context ? (
            <p>
              冻结研究上下文：{decisionDraft.research_context.source} · {decisionDraft.research_context.verification}
              · {decisionDraft.research_context.derived_from_chain_versions.join("；") || "NO_UPSTREAM_RECORD"}
            </p>
          ) : null}
          <p role="status">未持久化；需要后端命名命令与人工 Gate 才能成为正式决定。</p>
        </output>
      ) : null}
    </section>
  );
}
