import { useEffect, useState } from "react";

type Props = { commerceBaseUrl?: string };
type GiftState = "idle" | "loading" | "sending" | "active" | "reversing" | "reversed" | "error";
type Gift = { ref: string; name: string; amount: number; symbol: string };
type Balance = {
  purchase_ref: string;
  cash: number;
  settlement: number;
  entitlement: "ACTIVE" | "REVOKED";
  source: "SANDBOX_SYNTHETIC";
  fixture_only: true;
  external_effect: false;
};
type Settlement = {
  purchase_ref: string;
  track: "CONTENT_SUPPORT";
  currency: "CNY_CENT";
  entitlement: "ACTIVE" | "REVOKED";
  beneficiaries: Array<{ beneficiary_ref: string; net_amount: number }>;
  total: number;
  source: "SANDBOX_SYNTHETIC";
  fixture_only: true;
  external_effect: false;
};

const GIFTS: Gift[] = [
  { ref: "orange-lamp", name: "小橘灯", amount: 100, symbol: "✦" },
  { ref: "companionship", name: "陪伴花束", amount: 500, symbol: "❋" },
  { ref: "expert-stage", name: "专家星光", amount: 2_000, symbol: "✺" },
];
const STORAGE_KEY = "xiaojudeng.sandbox.gift.purchase_ref";
const ACTOR_HEADERS = {
  "Content-Type": "application/json",
  "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
  "X-Fixture-Only": "true",
  "X-Tenant-Id": "tenant.synthetic.alpha",
  "X-Family-Id": "family.synthetic.alpha",
  "X-Actor-Id": "actor.synthetic.adult",
  "X-Actor-Role": "ADULT_VIEWER",
};

export function LiveGiftSupport({ commerceBaseUrl }: Props) {
  const [selected, setSelected] = useState(GIFTS[0]);
  const [state, setState] = useState<GiftState>("idle");
  const [purchaseRef, setPurchaseRef] = useState("");
  const [balance, setBalance] = useState<Balance | null>(null);
  const [settlement, setSettlement] = useState<Settlement | null>(null);
  const adapterReady = Boolean(commerceBaseUrl && isLocalUrl(commerceBaseUrl));

  useEffect(() => {
    if (!commerceBaseUrl || !isLocalUrl(commerceBaseUrl)) return;
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return;
    setState("loading");
    void loadGiftEvidence(commerceBaseUrl, stored)
      .then(([nextBalance, nextSettlement]) => {
        setPurchaseRef(stored);
        setBalance(nextBalance);
        setSettlement(nextSettlement);
        setState(nextBalance.entitlement === "ACTIVE" ? "active" : "reversed");
      })
      .catch(() => setState("error"));
  }, [commerceBaseUrl]);

  return (
    <article className="live-gift-support" aria-labelledby="live-gift-heading">
      <h3 id="live-gift-heading">成人礼物支持</h3>
      <p>借鉴直播礼物的即时反馈，但不做榜单、攀比或优先提问；仅成人可操作。</p>
      <div className="live-gift-catalog" aria-label="礼物选择">
        {GIFTS.map((gift) => (
          <button
            aria-pressed={selected.ref === gift.ref}
            disabled={state === "sending" || state === "active" || state === "reversing"}
            key={gift.ref}
            type="button"
            onClick={() => setSelected(gift)}
          >
            <span aria-hidden="true">{gift.symbol}</span>
            <strong>{gift.name}</strong>
            <small>¥{formatCny(gift.amount)}</small>
          </button>
        ))}
      </div>
      {state === "idle" || state === "error" ? (
        <button type="button" disabled={!adapterReady} onClick={() => void sendGift()}>
          赠送{selected.name}（演示）
        </button>
      ) : null}
      {state === "loading" ? <span role="status">正在读取礼物支持记录…</span> : null}
      {state === "sending" ? <span role="status">正在记录礼物支持…</span> : null}
      {state === "active" && balance && settlement ? (
        <div className="live-offering-receipt" role="status">
          <div>
            <strong>{selected.name}已送达（演示），没有真实扣款。</strong>
            <p>
              专家 ¥{formatCny(beneficiary(settlement, "expert.synthetic.1"))} · 平台 ¥
              {formatCny(beneficiary(settlement, "platform:aifamily"))}
            </p>
          </div>
          <button type="button" onClick={() => void reverseGift()}>撤销礼物演示记录</button>
        </div>
      ) : null}
      {state === "reversing" ? <span role="status">正在撤销礼物记录…</span> : null}
      {state === "reversed" ? <strong role="status">礼物记录已撤销，待结算归零。</strong> : null}
      {state === "error" ? <span role="alert">礼物服务不可用，没有产生扣款或权益变化。</span> : null}
      <small>SANDBOX_SYNTHETIC · fixture_only=true · 无真实支付</small>
    </article>
  );

  async function sendGift() {
    if (!commerceBaseUrl || !isLocalUrl(commerceBaseUrl)) return;
    const ref = `gift.ui.${selected.ref}.${Date.now()}`;
    setState("sending");
    try {
      const purchase = await request(`${commerceBaseUrl}/sandbox/live-commerce/purchases`, {
        method: "POST",
        headers: ACTOR_HEADERS,
        body: JSON.stringify({
          purchase_ref: ref,
          track: "CONTENT_SUPPORT",
          subject_ref: `gift.synthetic.${selected.ref}`,
          amount: selected.amount,
          currency: "CNY_CENT",
          idempotency_key: ref,
        }),
      }) as Record<string, unknown>;
      if (purchase.purchase_ref !== ref || purchase.track !== "CONTENT_SUPPORT") {
        throw new Error("gift purchase receipt mismatch");
      }
      const [nextBalance, nextSettlement] = await loadGiftEvidence(commerceBaseUrl, ref);
      if (nextBalance.entitlement !== "ACTIVE" || nextSettlement.total !== selected.amount) {
        throw new Error("gift allocation mismatch");
      }
      localStorage.setItem(STORAGE_KEY, ref);
      setPurchaseRef(ref);
      setBalance(nextBalance);
      setSettlement(nextSettlement);
      setState("active");
    } catch {
      setState("error");
    }
  }

  async function reverseGift() {
    if (!commerceBaseUrl || !purchaseRef) return;
    setState("reversing");
    try {
      await request(
        `${commerceBaseUrl}/sandbox/live-commerce/purchases/${encodeURIComponent(purchaseRef)}/reversals`,
        {
          method: "POST",
          headers: ACTOR_HEADERS,
          body: JSON.stringify({
            reversal_ref: `gift-reversal.ui.${Date.now()}`,
            idempotency_key: `gift-reversal:${purchaseRef}`,
            reason: "adult reversed synthetic gift support",
          }),
        },
      );
      const [nextBalance, nextSettlement] = await loadGiftEvidence(commerceBaseUrl, purchaseRef);
      if (nextBalance.entitlement !== "REVOKED" || nextSettlement.total !== 0) {
        throw new Error("gift reversal evidence mismatch");
      }
      localStorage.removeItem(STORAGE_KEY);
      setBalance(nextBalance);
      setSettlement(nextSettlement);
      setState("reversed");
    } catch {
      setState("error");
    }
  }
}

async function loadGiftEvidence(baseUrl: string, purchaseRef: string): Promise<[Balance, Settlement]> {
  const [balance, settlement] = await Promise.all([
    request(`${baseUrl}/sandbox/live-commerce/purchases/${encodeURIComponent(purchaseRef)}/balances`, { headers: ACTOR_HEADERS }),
    request(`${baseUrl}/sandbox/live-commerce/purchases/${encodeURIComponent(purchaseRef)}/settlements`, { headers: ACTOR_HEADERS }),
  ]);
  return [parseBalance(balance, purchaseRef), parseSettlement(settlement, purchaseRef)];
}

async function request(url: string, init: RequestInit): Promise<unknown> {
  const response = await fetch(url, { ...init, cache: "no-store" });
  if (!response.ok) throw new Error(`gift request rejected: ${response.status}`);
  return response.json();
}

function parseBalance(value: unknown, purchaseRef: string): Balance {
  const record = asRecord(value);
  if (!safeEnvelope(record) || record.purchase_ref !== purchaseRef ||
    !Number.isFinite(record.cash) || !Number.isFinite(record.settlement) ||
    !["ACTIVE", "REVOKED"].includes(String(record.entitlement))) {
    throw new Error("unsafe gift balance");
  }
  return record as Balance;
}

function parseSettlement(value: unknown, purchaseRef: string): Settlement {
  const record = asRecord(value);
  if (!safeEnvelope(record) || record.purchase_ref !== purchaseRef ||
    record.track !== "CONTENT_SUPPORT" || record.currency !== "CNY_CENT" ||
    !["ACTIVE", "REVOKED"].includes(String(record.entitlement)) ||
    !Number.isFinite(record.total) || !Array.isArray(record.beneficiaries) ||
    record.beneficiaries.some((item) => {
      const beneficiaryRecord = asRecord(item);
      return typeof beneficiaryRecord.beneficiary_ref !== "string" ||
        !Number.isFinite(beneficiaryRecord.net_amount);
    })) {
    throw new Error("unsafe gift settlement");
  }
  return record as Settlement;
}

function safeEnvelope(record: Record<string, unknown>): boolean {
  return record.source === "SANDBOX_SYNTHETIC" &&
    record.fixture_only === true && record.external_effect === false;
}

function asRecord(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null) throw new Error("object response required");
  return value as Record<string, unknown>;
}

function beneficiary(settlement: Settlement, ref: string): number {
  return settlement.beneficiaries.find((item) => item.beneficiary_ref === ref)?.net_amount ?? 0;
}

function formatCny(cents: number): string {
  return (cents / 100).toFixed(2);
}

function isLocalUrl(value: string): boolean {
  try {
    return ["localhost", "127.0.0.1"].includes(new URL(value).hostname);
  } catch {
    return false;
  }
}
