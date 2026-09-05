import type { OpportunityLineage } from "./decisionApi";
import { EvidenceCoveragePanel } from "./EvidenceCoveragePanel";
import type { EvidenceCoverage } from "./evidenceCoverage";

type Props = {
  conceptTitle: string;
  conceptRef?: string;
  lineage: OpportunityLineage;
  onReturnToResearch?: (coverage: EvidenceCoverage) => void;
};

function refs(values: string[]): string {
  return values.length ? values.join("、") : "无已返回引用";
}

export function OpportunityLineagePanel({ conceptTitle, conceptRef, lineage, onReturnToResearch }: Props) {
  return (
    <details className="opportunity-lineage">
      <summary>查看 {conceptTitle} 的 Evidence → Opportunity 血缘</summary>
      <div className="opportunity-lineage-state" role="status">
        <strong>{lineage.completeness}</strong>
        <span>{lineage.review_state}</span>
      </div>

      <EvidenceCoveragePanel
        conceptTitle={conceptTitle}
        conceptRef={conceptRef}
        lineage={lineage}
        onReturnToResearch={onReturnToResearch}
      />

      <ol aria-label={`${conceptTitle} Opportunity 血缘节点`}>
        <li>
          <span className="semantic-label semantic-fact">FACT · 来源记录</span>
          <h4>MarketSignal</h4>
          {lineage.market_signal ? (
            <><p>{lineage.market_signal.raw_text}</p><code>{lineage.market_signal.id} · v{lineage.market_signal.version} · {lineage.market_signal.status}</code><small>来源引用：{lineage.market_signal.source_ref ?? "未提供"}</small><small>证据引用：{refs(lineage.market_signal.evidence_refs)}</small></>
          ) : <p>LINEAGE_INCOMPLETE：chain 未返回 MarketSignal。</p>}
        </li>
        <li>
          <span className="semantic-label semantic-fact">FACT · 洞察记录存在</span>
          <span className="semantic-label semantic-inference">INFERENCE · 洞察内容</span>
          <h4>CustomerInsight</h4>
          {lineage.customer_insight ? (
            <><p>{lineage.customer_insight.statement}</p><code>{lineage.customer_insight.id} · v{lineage.customer_insight.version} · {lineage.customer_insight.status}</code><small>证据引用：{refs(lineage.customer_insight.evidence_refs)}</small>{lineage.customer_insight.ai_provenance ? <small>AI provenance：{lineage.customer_insight.ai_provenance.generated_by} · {lineage.customer_insight.ai_provenance.model_ref} · {lineage.customer_insight.ai_provenance.prompt_use_case_version} · confidence {lineage.customer_insight.ai_provenance.confidence}（仅模型元数据）</small> : null}</>
          ) : <p>LINEAGE_INCOMPLETE：chain 未返回 CustomerInsight。</p>}
        </li>
        <li>
          <span className="semantic-label semantic-fact">FACT · Opportunity 记录存在</span>
          <span className="semantic-label semantic-inference">INFERENCE · 机会内容</span>
          <h4>Opportunity</h4>
          {lineage.opportunity ? (
            <>
              <p>{lineage.opportunity.statement}</p>
              <code>{lineage.opportunity.id} · v{lineage.opportunity.version}</code>
              <small>遗留领域状态：{lineage.opportunity.status}；它不是已证明的人工决定。</small>
              <small>证据引用：{refs(lineage.opportunity.evidence_refs)}</small>
              {lineage.opportunity.ai_provenance ? <small>AI provenance：{lineage.opportunity.ai_provenance.generated_by} · {lineage.opportunity.ai_provenance.model_ref} · {lineage.opportunity.ai_provenance.prompt_use_case_version} · confidence {lineage.opportunity.ai_provenance.confidence}（仅模型元数据）</small> : null}
            </>
          ) : <p>LINEAGE_INCOMPLETE：尚无 Opportunity，不以默认 WATCH 代替。</p>}
        </li>
        <li>
          <span className="semantic-label semantic-recommendation">RECOMMENDATION · 当前合同缺失</span>
          <h4>Opportunity Recommendation</h4>
          <p>现有 chain 没有独立建议对象；Web 不根据状态、证据数量或三区分数补算建议。</p>
        </li>
        <li>
          <span className="semantic-label semantic-human">HUMAN_DECISION · 待治理</span>
          <h4>人工机会决定</h4>
          <p>NEEDS_HUMAN_DECISION：现有合同没有 decision_id、决策人、理由、时间或证据快照。</p>
        </li>
      </ol>

      <section aria-label={`${conceptTitle} 下游缺口`} className="opportunity-lineage-gaps">
        <h4>进入 ProductPackage 前仍需补齐</h4>
        <ul>{lineage.reason_codes.map((reason) => <li key={reason}><code>{reason}</code></li>)}</ul>
      </section>
    </details>
  );
}
