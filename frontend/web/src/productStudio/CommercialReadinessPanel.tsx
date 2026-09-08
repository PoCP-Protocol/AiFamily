import { useState } from "react";
import { fetchCommercialReadiness, type CommercialReadiness } from "./commercialReadinessApi";

const labels: Record<string, string> = {
  lesson_scope_valid: "产品课时范围有效",
  courseware_approved: "课件已审批",
  product_package_released: "产品包已发布",
  evidence_verified: "证据已验证",
  payment_sandbox_verified: "支付沙箱已验证",
  entitlement_grant_verified: "权益发放已验证",
  delivery_readback_verified: "交付读回已验证",
  refund_recovery_verified: "退款恢复已验证",
  human_gate_accepted: "人工闸门已接受",
};

export function CommercialReadinessPanel() {
  const [result, setResult] = useState<CommercialReadiness | null>(null);
  const [lessonCount, setLessonCount] = useState<4 | 24>(24);
  const [evidenceRefs, setEvidenceRefs] = useState("");
  const [error, setError] = useState<string | null>(null);
  const evaluate = async () => {
    setError(null);
    try {
      const refs = [...new Set(evidenceRefs.split("\n").map((ref) => ref.trim()).filter(Boolean))];
      setResult(await fetchCommercialReadiness({ lesson_count: lessonCount, evidence_refs: refs, courseware_approved: true, product_package_released: true, evidence_verified: true, payment_sandbox_verified: false, entitlement_grant_verified: false, delivery_readback_verified: false, refund_recovery_verified: false, human_gate_accepted: true }));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "评估失败"); }
  };
  return <section aria-label="Commercial readiness" className="panel commercial-readiness-panel">
    <p className="section-kicker">商业化 Gate · 证据评估</p>
    <h2>{lessonCount === 4 ? "21天成长营商业化就绪度" : "24 节课程商业化就绪度"}</h2>
    <p className="muted">评估不会创建订单、收款或发放权益。</p>
    <label>产品范围<select aria-label="产品范围" value={lessonCount} onChange={(event) => setLessonCount(Number(event.target.value) as 4 | 24)}><option value={4}>21天成长营（4节）</option><option value={24}>24节完整课程</option></select></label>
    <label>证据引用（每行一条）<textarea aria-label="证据引用" rows={3} value={evidenceRefs} onChange={(event) => setEvidenceRefs(event.target.value)} placeholder="evidence:payment-sandbox@v1" /></label>
    <button className="secondary-button" onClick={evaluate} type="button">评估当前证据</button>
    {error && <p role="alert" className="status status-timeout">{error}</p>}
    {result && <div className="commercial-readiness-result" data-ready={result.ready}>
      <strong>{result.ready ? "可进入商业化 Gate" : "暂不可商业化"}</strong>
      <p>范围：<code>{result.scope}</code></p>
      <ul>{Object.entries(result.checks).map(([key, passed]) => <li key={key}>{passed ? "✓" : "×"} {labels[key] ?? key}</li>)}</ul>
      <p>证据引用：</p>
      {result.evidence_refs.length > 0 ? <ul aria-label="商业化证据引用">{result.evidence_refs.map((ref) => <li key={ref}><code>{ref}</code></li>)}</ul> : <p className="muted">暂无证据引用</p>}
      {!result.ready && <p className="muted">阻塞：{result.blockers.join("、")}</p>}
    </div>}
  </section>;
}
