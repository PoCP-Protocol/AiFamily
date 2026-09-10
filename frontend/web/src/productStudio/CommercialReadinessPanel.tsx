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
  const [checks, setChecks] = useState({
    courseware_approved: true,
    product_package_released: true,
    evidence_verified: true,
    payment_sandbox_verified: false,
    entitlement_grant_verified: false,
    delivery_readback_verified: false,
    refund_recovery_verified: false,
    human_gate_accepted: true,
  });
  const [error, setError] = useState<string | null>(null);
  const evaluate = async () => {
      setError(null);
      try {
        const refs = [...new Set(evidenceRefs.split("\n").map((ref) => ref.trim()).filter(Boolean))];
        if (refs.length === 0 || refs.some((ref) => !/@v[1-9][0-9]*$/.test(ref))) {
          throw new Error("证据引用必须使用带版本的格式，例如 evidence:payment@v1");
        }
      setResult(await fetchCommercialReadiness({ lesson_count: lessonCount, evidence_refs: refs, ...checks }));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "评估失败"); }
  };
  return <section aria-label="Commercial readiness" className="panel commercial-readiness-panel">
    <p className="section-kicker">商业化 Gate · 证据评估</p>
    <h2>{lessonCount === 4 ? "21天成长营商业化就绪度" : "24 节课程商业化就绪度"}</h2>
    <p className="muted">评估不会创建订单、收款或发放权益。</p>
    <label>产品范围<select aria-label="产品范围" value={lessonCount} onChange={(event) => setLessonCount(Number(event.target.value) as 4 | 24)}><option value={4}>21天成长营（4节）</option><option value={24}>24节完整课程</option></select></label>
    <label>证据引用（每行一条）<textarea aria-label="证据引用" rows={3} value={evidenceRefs} onChange={(event) => setEvidenceRefs(event.target.value)} placeholder="evidence:payment-sandbox@v1" /></label>
    <fieldset><legend>商业化证据状态</legend>{Object.entries(checks).map(([key, value]) => <label key={key}><input type="checkbox" checked={value} onChange={(event) => setChecks((current) => ({ ...current, [key]: event.target.checked }))} /> {labels[key] ?? key}</label>)}</fieldset>
    <p className="muted">勾选仅代表本次评估输入，不会自动生成事实、订单、支付或权益；最终准入仍需真实验收证据与人工 Gate。</p>
    <p className="muted" aria-label="当前选中的商业化证据状态">已选：{Object.entries(checks).filter(([, value]) => value).map(([key]) => labels[key] ?? key).join("、") || "无"}</p>
    <button className="secondary-button" onClick={evaluate} type="button">评估当前证据</button>
    {error && <p role="alert" className="status status-timeout">{error}</p>}
    {result && <div className="commercial-readiness-result" data-ready={result.ready}>
      <strong>{result.ready ? "可进入商业化 Gate" : "暂不可商业化"}</strong>
      <p className="muted">执行模式：{result.execution_mode}（不收款、不创建订单）</p>
      <p className="muted">评估时间：{new Date(result.evaluated_at).toLocaleString()}</p>
      <p>范围：<code>{result.scope}</code></p>
      <ul>{Object.entries(result.checks).map(([key, passed]) => <li key={key}>{passed ? "✓" : "×"} {labels[key] ?? key}</li>)}</ul>
      <p>证据引用：</p>
      {result.evidence_refs.length > 0 ? <ul aria-label="商业化证据引用">{result.evidence_refs.map((ref) => <li key={ref}><code>{ref}</code></li>)}</ul> : <p className="muted">暂无证据引用</p>}
      {!result.ready && <p className="muted">阻塞：{result.blockers.join("、")}</p>}
    </div>}
  </section>;
}
