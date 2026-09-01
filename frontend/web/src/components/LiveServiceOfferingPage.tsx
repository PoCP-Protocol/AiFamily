import { useState } from "react";

type Props = { commerceBaseUrl?: string };

type SupportReceipt = {
  intent_ref: string;
  external_effect: false;
  source: "SANDBOX_SYNTHETIC";
  fixture_only: true;
};

const ACTOR_HEADERS = {
  "Content-Type": "application/json",
  "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
  "X-Fixture-Only": "true",
  "X-Tenant-Id": "tenant.synthetic.alpha",
  "X-Family-Id": "family.synthetic.alpha",
  "X-Actor-Id": "actor.synthetic.adult",
  "X-Actor-Role": "ADULT_VIEWER",
};

export function LiveServiceOfferingPage({ commerceBaseUrl }: Props) {
  const [supportState, setSupportState] = useState<"idle" | "sending" | "sent" | "refunding" | "refunded" | "error">("idle");
  const [supportIntentRef, setSupportIntentRef] = useState("");

  return (
    <main className="live-offering-shell" aria-labelledby="live-offering-heading">
      <a className="live-inline-back" href="#live-home">← 返回小橘灯直播</a>
      <div className="live-offering-hero">
        <div>
          <p className="live-kicker">成人主动进入 · 服务方案演示</p>
          <h2 id="live-offering-heading">家庭沟通 · 30分钟专家咨询</h2>
          <p>适合看完直播后，希望针对一个具体家庭场景获得真人梳理的家长或照护者。</p>
        </div>
        <div className="live-offering-price">
          <span>服务价格</span>
          <strong>¥99</strong>
          <small>Sandbox，不会扣款</small>
        </div>
      </div>

      <section className="live-offering-grid" aria-label="服务内容与交易说明">
        <article className="live-offering-support-card">
          <p className="live-kicker">A · 内容支持</p>
          <h3>自愿支持本场内容 · ¥5</h3>
          <p>专家获得¥4，平台内容与技术服务费¥1。不会获得优先提问、私聊、预约或其他服务权利。</p>
          <p>不支持也不会影响观看、提问、回看或安全求助。</p>
          {supportState === "idle" || supportState === "error" ? (
            <button type="button" disabled={!commerceBaseUrl} onClick={() => void supportContent()}>
              记录内容支持（演示）
            </button>
          ) : null}
          {supportState === "sending" ? <span role="status">正在校验成人权限与账本…</span> : null}
          {supportState === "sent" ? (
            <div className="live-offering-receipt" role="status">
              <strong>内容支持意向已记录；Sandbox未发生真实扣款。</strong>
              <button type="button" onClick={() => void refundContent()}>撤销并退款（演示）</button>
            </div>
          ) : null}
          {supportState === "refunding" ? <span role="status">正在冲正全部分配…</span> : null}
          {supportState === "refunded" ? <strong role="status">内容支持已撤销，专家与平台分配均已冲正。</strong> : null}
          {supportState === "error" ? <span role="alert">支持服务不可用，未产生扣款。</span> : null}
        </article>
        <article>
          <p className="live-kicker">B · ServiceOffering购买</p>
          <h3>你会获得</h3>
          <ul>
            <li>一次30分钟一对一成人咨询</li>
            <li>围绕一个明确问题形成下一步行动建议</li>
            <li>咨询后可查看本次服务记录</li>
          </ul>
        </article>
        <article>
          <h3>你不会获得</h3>
          <ul>
            <li>直播间优先提问或插队权</li>
            <li>任何治疗、诊断或结果承诺</li>
            <li>孩子画像营销或自动推荐</li>
          </ul>
        </article>
        <article>
          <p className="live-kicker">C · 平台积分</p>
          <h3>非现金积分，当前未开放</h3>
          <p>积分不等同人民币、不可提现。正式开放前必须明确来源、用途、有效期和退回规则，并使用独立积分凭证。</p>
        </article>
        <article>
          <h3>费用如何分配</h3>
          <dl>
            <div><dt>专家服务费</dt><dd>¥79.20</dd></div>
            <div><dt>平台服务费</dt><dd>¥19.80</dd></div>
            <div><dt>发票</dt><dd>实际支付后按订单申请</dd></div>
          </dl>
        </article>
        <article>
          <h3>取消、退款与投诉</h3>
          <p>服务开始前24小时可全额取消；专家未履约可申请全额退款。争议由人工客服复核，不由AI自动裁决。</p>
        </article>
      </section>

      <section className="live-offering-gate" aria-label="服务接口状态">
        <div>
          <strong>当前仅供理解验证</strong>
          <p>预约、Consent、订单、支付与履约接口尚未接入，因此不会创建订单或联系专家。</p>
        </div>
        <button type="button" disabled>暂不可预约</button>
      </section>
    </main>
  );

  async function supportContent() {
    if (!commerceBaseUrl || !isLocalUrl(commerceBaseUrl)) return;
    const reference = `support.content.${Date.now()}`;
    setSupportState("sending");
    try {
      const response = await fetch(
        `${commerceBaseUrl}/sandbox/live-commerce/sessions/media.synthetic.1/support`,
        {
          method: "POST",
          headers: ACTOR_HEADERS,
          body: JSON.stringify({
            intent_ref: reference,
            idempotency_key: reference,
            kind: "TIP",
            amount: 500,
            currency: "CNY_CENT",
          }),
        },
      );
      if (!response.ok) throw new Error("support rejected");
      const receipt = (await response.json()) as SupportReceipt;
      if (receipt.source !== "SANDBOX_SYNTHETIC" || receipt.fixture_only !== true || receipt.external_effect !== false) {
        throw new Error("support receipt rejected");
      }
      setSupportIntentRef(receipt.intent_ref);
      setSupportState("sent");
    } catch {
      setSupportState("error");
    }
  }

  async function refundContent() {
    if (!commerceBaseUrl || !supportIntentRef || !isLocalUrl(commerceBaseUrl)) return;
    const reference = `refund.content.${Date.now()}`;
    setSupportState("refunding");
    try {
      const response = await fetch(`${commerceBaseUrl}/sandbox/live-commerce/refunds`, {
        method: "POST",
        headers: ACTOR_HEADERS,
        body: JSON.stringify({
          refund_ref: reference,
          support_intent_ref: supportIntentRef,
          idempotency_key: reference,
          reason: "adult withdrew sandbox content support",
        }),
      });
      if (!response.ok) throw new Error("refund rejected");
      const receipt = (await response.json()) as { status: string; external_effect: boolean };
      if (receipt.status !== "SANDBOX_REVERSED" || receipt.external_effect !== false) {
        throw new Error("refund receipt rejected");
      }
      setSupportState("refunded");
    } catch {
      setSupportState("error");
    }
  }
}

function isLocalUrl(value: string): boolean {
  try {
    return ["localhost", "127.0.0.1"].includes(new URL(value).hostname);
  } catch {
    return false;
  }
}
