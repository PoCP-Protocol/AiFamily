import type { OpportunityLineage } from "./decisionApi";
import { deriveEvidenceCoverage, type EvidenceCoverage } from "./evidenceCoverage";

type Props = {
  conceptTitle: string;
  conceptRef?: string;
  lineage: OpportunityLineage;
  onReturnToResearch?: (coverage: EvidenceCoverage) => void;
};

const STATUS_LABELS = {
  NOT_RETURNED: "记录未返回",
  PRESENT_WITHOUT_REFS: "记录已返回，引用为空",
  PRESENT_WITH_REFS: "已返回引用（未验证）",
} as const;

export function EvidenceCoveragePanel({ conceptTitle, conceptRef, lineage, onReturnToResearch }: Props) {
  const coverage = deriveEvidenceCoverage(lineage);
  return (
    <section className="evidence-coverage" aria-label={`${conceptTitle} 证据引用覆盖`}>
      <h4>证据引用覆盖</h4>
      <p><strong>来源：</strong><code>{coverage.source}</code>（客户端依据 chain 响应派生）</p>
      <p><strong>结构：</strong><code>{coverage.structure}</code></p>
      <p><strong>验证：</strong><code>{coverage.verification}</code></p>
      <ul>
        {coverage.nodes.map(({ node, status, reason_code }) => (
          <li key={node}>
            <strong>{node} · {STATUS_LABELS[status]}</strong>
            <code>{status}</code>
            {reason_code ? <small>{reason_code}</small> : null}
          </li>
        ))}
      </ul>
      <p className="muted">引用存在不代表真实性、适用性或有效期已验证；ProductPackage 仍须 receipt-backed admission 与 Human Gate。</p>
      {onReturnToResearch ? (
        <button
          type="button"
          className="text-button"
          aria-label={`带入退回研究：${conceptTitle}${conceptRef ? `（${conceptRef}）` : ""}`}
          onClick={() => onReturnToResearch(coverage)}
        >
          带入退回研究：{conceptTitle}
        </button>
      ) : null}
    </section>
  );
}
