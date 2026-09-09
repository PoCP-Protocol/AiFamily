import { useState } from "react";
import { HttpCommerceProjectionApiClient, type CommerceProjection, type CommerceProjectionApiClient } from "./commerceProjectionApi";

export function CommerceProjectionPanel({ client }: { client?: CommerceProjectionApiClient }) {
  const [familyId, setFamilyId] = useState("family-demo"); const [projection, setProjection] = useState<CommerceProjection | null>(null); const [error, setError] = useState<string | null>(null); const [loading, setLoading] = useState(false);
  const read = async () => { setLoading(true); setError(null); try { setProjection(await (client ?? new HttpCommerceProjectionApiClient()).get(familyId.trim())); } catch (cause) { setError(cause instanceof Error ? cause.message : "读取失败"); } finally { setLoading(false); } };
  return <section aria-label="Commerce delivery projection" className="panel commerce-projection-panel">
    <p className="section-kicker">Commerce · Web 交付回读</p><h2>家庭权益与退款恢复状态</h2>
    <p className="muted">只读投影：不会收款、创建订单或修改权益；状态来自服务端持久化读模型。</p>
    <label>家庭 ID<input aria-label="家庭 ID" value={familyId} onChange={(event) => setFamilyId(event.target.value)} /></label>
    <button className="secondary-button" disabled={loading || !familyId.trim()} onClick={read} type="button">{loading ? "读取中…" : "读取交付状态"}</button>
    {error && <p role="alert" className="status status-timeout">{error}</p>}
    {projection && <div aria-live="polite"><p>范围：<code>{projection.family_id}</code> · {projection.visibility} · projection v{projection.projection_version}</p>
      <h3>订单意向（{projection.order_intents.length}）</h3><ul>{projection.order_intents.map((item) => <li key={item.order_intent_id}><code>{item.product_ref}</code> · {item.status}</li>)}</ul>
      <h3>权益（{projection.entitlements.length}）</h3><ul>{projection.entitlements.map((item) => <li key={item.entitlement_id}><code>{item.entitlement_id}</code> · {item.status}</li>)}</ul>
      <p className="muted">{projection.text_equivalent}</p></div>}
  </section>;
}
