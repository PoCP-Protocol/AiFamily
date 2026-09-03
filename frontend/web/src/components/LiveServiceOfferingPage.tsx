import { useEffect, useState } from "react";

import { LiveGiftSupport } from "./LiveGiftSupport";

type Props = { commerceBaseUrl?: string };
type SupportState = "idle" | "sending" | "active" | "reversing" | "reversed" | "error";
type MembershipState = "idle" | "loading" | "sending" | "active" | "reversing" | "reversed" | "error";
type PointsState = MembershipState;

type SandboxResponse = {
  source: "SANDBOX_SYNTHETIC";
  fixture_only: true;
  external_effect: false;
};

type PurchaseReceipt = SandboxResponse & {
  purchase_ref: string;
  track: "CONTENT_SUPPORT" | "MEMBERSHIP" | "POINTS";
};

type BalanceReceipt = SandboxResponse & {
  purchase_ref: string;
  cash: number;
  settlement: number;
  entitlement: "ACTIVE" | "REVOKED";
};

type SettlementReceipt = SandboxResponse & {
  purchase_ref: string;
  track: "CONTENT_SUPPORT" | "MEMBERSHIP" | "MEDIA_ENTITLEMENT" | "SERVICE_OFFERING" | "POINTS";
  currency: "CNY_CENT" | "POINT";
  entitlement: "ACTIVE" | "REVOKED";
  beneficiaries: Array<{ beneficiary_ref: string; net_amount: number }>;
  total: number;
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

const CONTRACTS = {
  membership: "membership.synthetic.orange-light",
  media: "media-entitlement.synthetic.replay-1",
  service: "service-offering.synthetic.consultation-30m",
} as const;

const MEMBERSHIP_PURCHASE_REF_KEY = "xiaojudeng.sandbox.membership.purchase_ref";
const POINTS_PURCHASE_REF_KEY = "xiaojudeng.sandbox.points.purchase_ref";
const CONTENT_SUPPORT_PURCHASE_REF_KEY = "xiaojudeng.sandbox.content_support.purchase_ref";

export function LiveServiceOfferingPage({ commerceBaseUrl }: Props) {
  const [supportState, setSupportState] = useState<SupportState>("idle");
  const [supportPurchaseRef, setSupportPurchaseRef] = useState("");
  const [balance, setBalance] = useState<BalanceReceipt | null>(null);
  const [membershipState, setMembershipState] = useState<MembershipState>("idle");
  const [membershipPurchaseRef, setMembershipPurchaseRef] = useState("");
  const [membershipBalance, setMembershipBalance] = useState<BalanceReceipt | null>(null);
  const [pointsState, setPointsState] = useState<PointsState>("idle");
  const [pointsPurchaseRef, setPointsPurchaseRef] = useState("");
  const [pointsBalance, setPointsBalance] = useState<BalanceReceipt | null>(null);
  const [pointsSettlement, setPointsSettlement] = useState<SettlementReceipt | null>(null);
  const adapterReady = Boolean(commerceBaseUrl && isLocalUrl(commerceBaseUrl));

  useEffect(() => {
    if (!commerceBaseUrl || !isLocalUrl(commerceBaseUrl)) return;
    const storedPurchaseRef = localStorage.getItem(MEMBERSHIP_PURCHASE_REF_KEY);
    if (!storedPurchaseRef) return;
    setMembershipState("loading");
    void loadBalance(commerceBaseUrl, storedPurchaseRef)
      .then((refreshedBalance) => {
        setMembershipPurchaseRef(storedPurchaseRef);
        setMembershipBalance(refreshedBalance);
        setMembershipState(refreshedBalance.entitlement === "ACTIVE" ? "active" : "reversed");
      })
      .catch(() => setMembershipState("error"));
  }, [commerceBaseUrl]);

  useEffect(() => {
    if (!commerceBaseUrl || !isLocalUrl(commerceBaseUrl)) return;
    const storedPurchaseRef = localStorage.getItem(POINTS_PURCHASE_REF_KEY);
    if (!storedPurchaseRef) return;
    setPointsState("loading");
    void Promise.all([
      loadBalance(commerceBaseUrl, storedPurchaseRef),
      loadSettlement(commerceBaseUrl, storedPurchaseRef),
    ])
      .then(([refreshedBalance, refreshedSettlement]) => {
        setPointsPurchaseRef(storedPurchaseRef);
        setPointsBalance(refreshedBalance);
        setPointsSettlement(refreshedSettlement);
        setPointsState(refreshedBalance.entitlement === "ACTIVE" ? "active" : "reversed");
      })
      .catch(() => setPointsState("error"));
  }, [commerceBaseUrl]);

  return (
    <main className="live-offering-shell" aria-labelledby="live-offering-heading">
      <a className="live-inline-back" href="#live-home">← 返回小橘灯直播</a>

      <div className="live-offering-hero">
        <div>
          <p className="live-kicker">仅限成人 · 内容支持演示</p>
          <h2 id="live-offering-heading">支持这场内容</h2>
          <p>如果这场直播对你有帮助，可以留下 ¥5 的支持演示。不支持也不会影响观看、提问、回看或安全求助。</p>
        </div>
        <div className="live-offering-price">
          <span>本次支持</span>
          <strong>¥5</strong>
          <small>不会真实扣款</small>
        </div>
      </div>

      <section className="live-offering-grid" aria-label="内容支持与独立服务状态">
        <LiveGiftSupport commerceBaseUrl={commerceBaseUrl} />
        <article className="live-offering-support-card" data-contract-kind="CONTENT_SUPPORT">
          <h3>支持这场内容</h3>
          <p>专家演示分配 ¥4，平台内容与技术服务演示分配 ¥1；不会获得优先提问、私聊或预约权。</p>
          <p><strong>SANDBOX_SYNTHETIC · fixture_only=true</strong>，只写入本地演示账本，不产生真实资金或外部效果。</p>

          {supportState === "idle" || supportState === "error" ? (
            <button type="button" disabled={!adapterReady} onClick={() => void supportContent()}>
              支持这场内容（演示）
            </button>
          ) : null}
          {supportState === "sending" ? <span role="status">正在记录演示支持…</span> : null}
          {supportState === "active" && balance ? (
            <div className="live-offering-receipt" role="status">
              <div>
                <strong>演示记录已创建，没有真实扣款。</strong>
                <p>支持记录 ¥{formatCny(balance.cash)} · 分配记录 ¥{formatCny(balance.settlement)} · 状态：有效</p>
              </div>
              <button type="button" onClick={() => void reverseContentSupport()}>撤销演示记录</button>
            </div>
          ) : null}
          {supportState === "reversing" ? <span role="status">正在撤销演示记录…</span> : null}
          {supportState === "reversed" && balance ? (
            <strong role="status">演示记录已撤销：支持记录 ¥{formatCny(balance.cash)}，分配记录 ¥{formatCny(balance.settlement)}。</strong>
          ) : null}
          {supportState === "error" ? <span role="alert">本地演示服务不可用，没有产生扣款或权益变化。</span> : null}
        </article>

        <article data-contract-ref={CONTRACTS.membership}>
          <h3>会员权益</h3>
          <p>会员使用独立确认记录，不会因为支持本场内容自动开通，也不会影响观看、提问或回看。</p>
          <p><strong>SANDBOX_SYNTHETIC · fixture_only=true</strong>，不会真实扣款或产生外部效果。</p>
          {membershipState === "idle" || membershipState === "error" ? (
            <button type="button" disabled={!adapterReady} onClick={() => void activateMembership()}>
              开通小橘灯会员（演示）
            </button>
          ) : null}
          {membershipState === "loading" ? <span role="status">正在读取会员演示状态…</span> : null}
          {membershipState === "sending" ? <span role="status">正在开通会员演示…</span> : null}
          {membershipState === "active" && membershipBalance ? (
            <div className="live-offering-receipt" role="status">
              <div>
                <strong>会员权益：已开通（演示）</strong>
                <p>独立会员记录已生效，没有真实扣款。</p>
              </div>
              <button type="button" onClick={() => void reverseMembership()}>
                撤销会员演示记录
              </button>
            </div>
          ) : null}
          {membershipState === "reversing" ? <span role="status">正在撤销会员演示记录…</span> : null}
          {membershipState === "reversed" && membershipBalance ? (
            <strong role="status">会员权益：已撤销（演示）</strong>
          ) : null}
          {membershipState === "error" ? (
            <span role="alert">会员演示服务不可用，没有产生扣款或权益变化。</span>
          ) : null}
        </article>

        <article data-contract-ref={CONTRACTS.media}>
          <h3>付费内容</h3>
          <p><strong>状态：未开通</strong></p>
          <p>专题回看或付费媒体使用独立确认记录，不与内容支持共用凭证。</p>
        </article>

        <article data-contract-ref={CONTRACTS.service}>
          <h3>预约30分钟真人咨询</h3>
          <p><strong>状态：尚未预约</strong></p>
          <p>正式预约需单独确认服务、价格、时间、履约和取消规则。</p>
          <button type="button" disabled>暂不可预约</button>
        </article>

        <article id="live-points-info">
          <h3>了解平台积分</h3>
          <p>成人可以用 100 个合成积分支持本场专家；积分不是现金、不可提现，也不会购买优先提问权。</p>
          <p><strong>SANDBOX_SYNTHETIC · fixture_only=true</strong>，专家与平台分配分别记账，可撤销、可重启回读。</p>
          {pointsState === "idle" || pointsState === "error" ? (
            <button type="button" disabled={!adapterReady} onClick={() => void supportWithPoints()}>
              使用 100 积分支持专家（演示）
            </button>
          ) : null}
          {pointsState === "loading" ? <span role="status">正在读取积分支持状态…</span> : null}
          {pointsState === "sending" ? <span role="status">正在记录积分支持…</span> : null}
          {pointsState === "active" && pointsBalance && pointsSettlement ? (
            <div className="live-offering-receipt" role="status">
              <div>
                <strong>积分支持：已记录（演示）</strong>
                <p>
                  未发生现金交易 · 专家 {beneficiaryAmount(pointsSettlement, "expert.synthetic.1")} 积分 ·
                  平台 {beneficiaryAmount(pointsSettlement, "platform:aifamily")} 积分
                </p>
              </div>
              <button type="button" onClick={() => void reversePointsSupport()}>
                撤销积分支持
              </button>
            </div>
          ) : null}
          {pointsState === "reversing" ? <span role="status">正在撤销积分支持…</span> : null}
          {pointsState === "reversed" && pointsBalance && pointsSettlement ? (
            <strong role="status">积分支持已撤销：现金 ¥0.00，专家与平台待结算均为 0。</strong>
          ) : null}
          {pointsState === "error" ? (
            <span role="alert">积分演示服务不可用，没有产生现金、积分或结算变化。</span>
          ) : null}
        </article>
      </section>

      <section className="live-offering-gate" aria-label="演示边界">
        <div>
          <strong>每一种商业能力都使用独立凭证与可撤销状态</strong>
          <p>内容支持、会员、付费回看和积分互不冒充；真人咨询仍须单独确认服务、时间与取消规则。</p>
        </div>
      </section>
    </main>
  );

  async function supportContent() {
    if (!commerceBaseUrl || !isLocalUrl(commerceBaseUrl)) return;
    const purchaseRef = `content-support.ui.${Date.now()}`;
    setSupportState("sending");
    try {
      const purchase = await requestSandbox<PurchaseReceipt>(
        `${commerceBaseUrl}/sandbox/live-commerce/purchases`,
        {
          method: "POST",
          headers: ACTOR_HEADERS,
          body: JSON.stringify({
            purchase_ref: purchaseRef,
            track: "CONTENT_SUPPORT",
            subject_ref: "media.synthetic.1",
            amount: 500,
            currency: "CNY_CENT",
            idempotency_key: purchaseRef,
          }),
        },
      );
      if (purchase.purchase_ref !== purchaseRef || purchase.track !== "CONTENT_SUPPORT") {
        throw new Error("content support receipt mismatch");
      }
      const refreshedBalance = await loadBalance(commerceBaseUrl, purchaseRef);
      if (refreshedBalance.entitlement !== "ACTIVE") throw new Error("content support is not active");
      localStorage.setItem(CONTENT_SUPPORT_PURCHASE_REF_KEY, purchaseRef);
      setSupportPurchaseRef(purchaseRef);
      setBalance(refreshedBalance);
      setSupportState("active");
    } catch {
      setSupportState("error");
    }
  }

  async function reverseContentSupport() {
    if (!commerceBaseUrl || !supportPurchaseRef || !isLocalUrl(commerceBaseUrl)) return;
    const reversalRef = `content-support-reversal.ui.${Date.now()}`;
    setSupportState("reversing");
    try {
      await requestSandbox(
        `${commerceBaseUrl}/sandbox/live-commerce/purchases/${encodeURIComponent(supportPurchaseRef)}/reversals`,
        {
          method: "POST",
          headers: ACTOR_HEADERS,
          body: JSON.stringify({
            reversal_ref: reversalRef,
            idempotency_key: reversalRef,
            reason: "adult withdrew synthetic content support record",
          }),
        },
      );
      const refreshedBalance = await loadBalance(commerceBaseUrl, supportPurchaseRef);
      if (refreshedBalance.entitlement !== "REVOKED") throw new Error("content support is not revoked");
      setBalance(refreshedBalance);
      setSupportState("reversed");
    } catch {
      setSupportState("error");
    }
  }

  async function activateMembership() {
    if (!commerceBaseUrl || !isLocalUrl(commerceBaseUrl)) return;
    const purchaseRef = `membership.ui.${Date.now()}`;
    const idempotencyKey = `membership-idempotency.ui.${Date.now()}`;
    setMembershipState("sending");
    try {
      const purchase = await requestSandbox<PurchaseReceipt>(
        `${commerceBaseUrl}/sandbox/live-commerce/purchases`,
        {
          method: "POST",
          headers: ACTOR_HEADERS,
          body: JSON.stringify({
            purchase_ref: purchaseRef,
            track: "MEMBERSHIP",
            subject_ref: CONTRACTS.membership,
            amount: 3000,
            currency: "CNY_CENT",
            idempotency_key: idempotencyKey,
          }),
        },
      );
      if (purchase.purchase_ref !== purchaseRef || purchase.track !== "MEMBERSHIP") {
        throw new Error("membership receipt mismatch");
      }
      const refreshedBalance = await loadBalance(commerceBaseUrl, purchaseRef);
      if (refreshedBalance.entitlement !== "ACTIVE") throw new Error("membership is not active");
      localStorage.setItem(MEMBERSHIP_PURCHASE_REF_KEY, purchaseRef);
      setMembershipPurchaseRef(purchaseRef);
      setMembershipBalance(refreshedBalance);
      setMembershipState("active");
    } catch {
      setMembershipState("error");
    }
  }

  async function reverseMembership() {
    if (!commerceBaseUrl || !membershipPurchaseRef || !isLocalUrl(commerceBaseUrl)) return;
    const reversalRef = `membership-reversal.ui.${Date.now()}`;
    setMembershipState("reversing");
    try {
      await requestSandbox(
        `${commerceBaseUrl}/sandbox/live-commerce/purchases/${encodeURIComponent(membershipPurchaseRef)}/reversals`,
        {
          method: "POST",
          headers: ACTOR_HEADERS,
          body: JSON.stringify({
            reversal_ref: reversalRef,
            idempotency_key: reversalRef,
            reason: "adult withdrew synthetic membership record",
          }),
        },
      );
      const refreshedBalance = await loadBalance(commerceBaseUrl, membershipPurchaseRef);
      if (refreshedBalance.entitlement !== "REVOKED") throw new Error("membership is not revoked");
      setMembershipBalance(refreshedBalance);
      setMembershipState("reversed");
    } catch {
      setMembershipState("error");
    }
  }

  async function supportWithPoints() {
    if (!commerceBaseUrl || !isLocalUrl(commerceBaseUrl)) return;
    const purchaseRef = `points-support.ui.${Date.now()}`;
    const idempotencyKey = `points-support-idempotency.ui.${Date.now()}`;
    setPointsState("sending");
    try {
      const purchase = await requestSandbox<PurchaseReceipt>(
        `${commerceBaseUrl}/sandbox/live-commerce/purchases`,
        {
          method: "POST",
          headers: ACTOR_HEADERS,
          body: JSON.stringify({
            purchase_ref: purchaseRef,
            track: "POINTS",
            subject_ref: "media.synthetic.1",
            amount: 100,
            currency: "POINT",
            idempotency_key: idempotencyKey,
          }),
        },
      );
      if (purchase.purchase_ref !== purchaseRef || purchase.track !== "POINTS") {
        throw new Error("points support receipt mismatch");
      }
      const [refreshedBalance, refreshedSettlement] = await Promise.all([
        loadBalance(commerceBaseUrl, purchaseRef),
        loadSettlement(commerceBaseUrl, purchaseRef),
      ]);
      if (
        refreshedBalance.entitlement !== "ACTIVE" ||
        refreshedBalance.cash !== 0 ||
        refreshedSettlement.total !== 100
      ) {
        throw new Error("points support is not active");
      }
      localStorage.setItem(POINTS_PURCHASE_REF_KEY, purchaseRef);
      setPointsPurchaseRef(purchaseRef);
      setPointsBalance(refreshedBalance);
      setPointsSettlement(refreshedSettlement);
      setPointsState("active");
    } catch {
      setPointsState("error");
    }
  }

  async function reversePointsSupport() {
    if (!commerceBaseUrl || !pointsPurchaseRef || !isLocalUrl(commerceBaseUrl)) return;
    const reversalRef = `points-support-reversal.ui.${Date.now()}`;
    setPointsState("reversing");
    try {
      await requestSandbox(
        `${commerceBaseUrl}/sandbox/live-commerce/purchases/${encodeURIComponent(pointsPurchaseRef)}/reversals`,
        {
          method: "POST",
          headers: ACTOR_HEADERS,
          body: JSON.stringify({
            reversal_ref: reversalRef,
            idempotency_key: reversalRef,
            reason: "adult withdrew synthetic points support",
          }),
        },
      );
      const [refreshedBalance, refreshedSettlement] = await Promise.all([
        loadBalance(commerceBaseUrl, pointsPurchaseRef),
        loadSettlement(commerceBaseUrl, pointsPurchaseRef),
      ]);
      if (refreshedBalance.entitlement !== "REVOKED" || refreshedSettlement.total !== 0) {
        throw new Error("points support is not revoked");
      }
      setPointsBalance(refreshedBalance);
      setPointsSettlement(refreshedSettlement);
      setPointsState("reversed");
    } catch {
      setPointsState("error");
    }
  }
}

async function loadBalance(baseUrl: string, purchaseRef: string): Promise<BalanceReceipt> {
  return await requestSandbox<BalanceReceipt>(
    `${baseUrl}/sandbox/live-commerce/purchases/${encodeURIComponent(purchaseRef)}/balances`,
    { headers: ACTOR_HEADERS },
  );
}

async function loadSettlement(baseUrl: string, purchaseRef: string): Promise<SettlementReceipt> {
  return await requestSandbox<SettlementReceipt>(
    `${baseUrl}/sandbox/live-commerce/purchases/${encodeURIComponent(purchaseRef)}/settlements`,
    { headers: ACTOR_HEADERS },
  );
}

async function requestSandbox<T extends SandboxResponse>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) throw new Error(`sandbox request rejected: ${response.status}`);
  const result = (await response.json()) as T;
  if (result.source !== "SANDBOX_SYNTHETIC" || result.fixture_only !== true || result.external_effect !== false) {
    throw new Error("sandbox evidence rejected");
  }
  return result;
}

function formatCny(amountInCents: number): string {
  return (amountInCents / 100).toFixed(2);
}

function beneficiaryAmount(receipt: SettlementReceipt, beneficiaryRef: string): number {
  return receipt.beneficiaries.find((item) => item.beneficiary_ref === beneficiaryRef)?.net_amount ?? 0;
}

function isLocalUrl(value: string): boolean {
  try {
    return ["localhost", "127.0.0.1"].includes(new URL(value).hostname);
  } catch {
    return false;
  }
}
