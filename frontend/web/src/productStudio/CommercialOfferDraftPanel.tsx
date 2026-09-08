import { useState } from "react";

type Offer = {
  offerId: string;
  packageRef: string;
  durationDays: 21 | 90;
  currency: string;
  price: string;
  entitlementRefs: string[];
  deliverySla: string;
  refundPolicyRef: string;
  evidenceRefs: string[];
};

const parseList = (value: string) => [...new Set(value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean))];

/** Browser-side proposal editor; it never creates an order or a customer fact. */
export function CommercialOfferDraftPanel() {
  const [offer, setOffer] = useState<Offer>({
    offerId: "offer:family-growth-21d-v1",
    packageRef: "product-package:family-growth-21d-v1",
    durationDays: 21,
    currency: "CNY",
    price: "199",
    entitlementRefs: ["entitlement:courseware", "entitlement:coach-checkin"],
    deliverySla: "工作日 24 小时内响应",
    refundPolicyRef: "policy:family-growth-standard-v1",
    evidenceRefs: ["verification-receipt:pilot-acceptance-v1"],
  });
  const [saved, setSaved] = useState(false);
  const update = <K extends keyof Offer>(key: K, value: Offer[K]) => { setSaved(false); setOffer((current) => ({ ...current, [key]: value })); };
  const ready = offer.offerId.trim() && offer.packageRef.trim() && Number(offer.price) > 0
    && offer.entitlementRefs.length > 0 && offer.evidenceRefs.length > 0;
  return (
    <section aria-label="Commercial Offer Draft" className="panel commercial-offer-draft-panel">
      <div className="section-kicker">ProductPackage → Commercial Offer DRAFT → Human Gate</div>
      <h2>21/90 天商业产品包草案</h2>
      <p className="muted">这里只编排报价与权益草案，不创建订单、不收款，也不把 AI 输出变成商业事实。</p>
      <div className="product-package-form-grid">
        <label>Offer ID<input value={offer.offerId} onChange={(e) => update("offerId", e.target.value)} /></label>
        <label>ProductPackage 引用<input value={offer.packageRef} onChange={(e) => update("packageRef", e.target.value)} /></label>
        <label>周期<select value={offer.durationDays} onChange={(e) => update("durationDays", Number(e.target.value) as 21 | 90)}><option value={21}>21 天成长营</option><option value={90}>90 天成长计划</option></select></label>
        <label>币种<input maxLength={3} value={offer.currency} onChange={(e) => update("currency", e.target.value.toUpperCase())} /></label>
        <label>试点价格<input min={0} step="0.01" type="number" value={offer.price} onChange={(e) => update("price", e.target.value)} /></label>
        <label>交付 SLA<input value={offer.deliverySla} onChange={(e) => update("deliverySla", e.target.value)} /></label>
        <label>退款政策引用<input value={offer.refundPolicyRef} onChange={(e) => update("refundPolicyRef", e.target.value)} /></label>
      </div>
      <div className="product-package-form-grid">
        <label>权益引用<textarea rows={2} value={offer.entitlementRefs.join("\n")} onChange={(e) => update("entitlementRefs", parseList(e.target.value))} /></label>
        <label>试点证据引用<textarea rows={2} value={offer.evidenceRefs.join("\n")} onChange={(e) => update("evidenceRefs", parseList(e.target.value))} /></label>
      </div>
      <button className="primary-button" disabled={!ready} onClick={() => setSaved(true)} type="button">保存为 DRAFT 草案</button>
      {saved ? <div aria-live="polite" className="callout" role="status"><strong>DRAFT · 未发布</strong><p>报价草案已保存在当前工作台状态，仍需人工商业 Gate、版权/安全审查和正式商务系统接管。</p></div> : null}
    </section>
  );
}
