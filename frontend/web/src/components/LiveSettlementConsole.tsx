import { useEffect, useState } from "react";

type Props = { commerceBaseUrl?: string };
type ConsoleState = "loading" | "ready" | "working" | "missing" | "error";
type SettlementState = "PENDING" | "APPROVED" | "REJECTED";

type SettlementRequestView = {
  request_ref: string;
  purchase_ref: string;
  beneficiary_ref: string;
  amount: number;
  currency: "CNY_CENT" | "POINT";
  state: SettlementState;
  requester_id: string;
  reviewer_id?: string | null;
  decision_reason?: string | null;
  payment_state: "NOT_EXECUTED";
  source: "SANDBOX_SYNTHETIC";
  fixture_only: true;
  external_effect: false;
};

const CONTENT_SUPPORT_PURCHASE_REF_KEY = "xiaojudeng.sandbox.content_support.purchase_ref";
const BASE_HEADERS = {
  "Content-Type": "application/json",
  "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
  "X-Fixture-Only": "true",
  "X-Tenant-Id": "tenant.synthetic.alpha",
  "X-Family-Id": "family.synthetic.alpha",
};
const CREATOR_HEADERS = {
  ...BASE_HEADERS,
  "X-Actor-Id": "actor.synthetic.creator.1",
  "X-Actor-Role": "CREATOR_OPERATOR",
};
const REVIEWER_HEADERS = {
  ...BASE_HEADERS,
  "X-Actor-Id": "actor.synthetic.finance",
  "X-Actor-Role": "HUMAN_FINANCE_REVIEWER",
};

export function LiveSettlementConsole({ commerceBaseUrl }: Props) {
  const [state, setState] = useState<ConsoleState>(commerceBaseUrl ? "loading" : "missing");
  const [requests, setRequests] = useState<SettlementRequestView[]>([]);
  const [purchaseRef] = useState(() => localStorage.getItem(CONTENT_SUPPORT_PURCHASE_REF_KEY) ?? "");
  const adapterReady = Boolean(commerceBaseUrl && isLocalUrl(commerceBaseUrl));

  useEffect(() => {
    if (!commerceBaseUrl || !isLocalUrl(commerceBaseUrl)) return;
    const controller = new AbortController();
    void loadRequests(commerceBaseUrl, controller.signal)
      .then((items) => {
        setRequests(items);
        setState("ready");
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) setState("error");
      });
    return () => controller.abort();
  }, [commerceBaseUrl]);

  return (
    <section className="live-ops-shell" aria-labelledby="live-settlement-heading">
      <header className="live-ops-heading">
        <div>
          <p className="live-kicker">Creator Ops · 人工财务闸门</p>
          <h2 id="live-settlement-heading">专家结算审核</h2>
          <p>待结算金额必须由专家申请、人工审批；批准也不会在 Sandbox 产生真实付款。</p>
        </div>
        <span>SANDBOX_SYNTHETIC</span>
      </header>

      {!purchaseRef ? (
        <p className="live-ops-state">成人完成一次内容支持后，专家才可提交对应结算申请。</p>
      ) : (
        <button
          type="button"
          disabled={!adapterReady || state === "working"}
          onClick={() => void createSettlementRequest()}
        >
          申请最近一笔专家结算（演示）
        </button>
      )}
      {state === "loading" ? <p className="live-ops-state">正在读取结算审核队列…</p> : null}
      {state === "missing" ? <p className="live-ops-state">结算审核服务暂不可用。</p> : null}
      {state === "error" ? <p className="live-ops-state">结算审核失败，没有产生付款。</p> : null}

      <div className="live-ops-list">
        {requests.map((request) => (
          <article className="live-ops-card" key={request.request_ref}>
            <div>
              <span>{request.state === "PENDING" ? "等待人工审批" : settlementStateLabel(request.state)}</span>
              <strong>专家待结算 {formatAmount(request.amount, request.currency)}</strong>
              <small>{request.purchase_ref}</small>
              <small>付款状态：未执行</small>
              {request.decision_reason ? <small>审核理由：{request.decision_reason}</small> : null}
            </div>
            {request.state === "PENDING" ? (
              <div className="live-ops-actions">
                <button type="button" onClick={() => void decide(request, "APPROVE")}>批准结算</button>
                <button
                  className="live-ops-reject"
                  type="button"
                  onClick={() => void decide(request, "REJECT")}
                >
                  拒绝结算
                </button>
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );

  async function createSettlementRequest() {
    if (!commerceBaseUrl || !purchaseRef || !isLocalUrl(commerceBaseUrl)) return;
    const requestRef = `settlement-request.ui.${Date.now()}`;
    setState("working");
    try {
      await requestSandbox<SettlementRequestView>(
        `${commerceBaseUrl}/sandbox/live-commerce/settlement-requests`,
        {
          method: "POST",
          headers: CREATOR_HEADERS,
          body: JSON.stringify({
            request_ref: requestRef,
            purchase_ref: purchaseRef,
            idempotency_key: requestRef,
            beneficiary_ref: "expert.synthetic.1",
          }),
        },
      );
      setRequests(await loadRequests(commerceBaseUrl));
      setState("ready");
    } catch {
      setState("error");
    }
  }

  async function decide(request: SettlementRequestView, action: "APPROVE" | "REJECT") {
    if (!commerceBaseUrl || !isLocalUrl(commerceBaseUrl)) return;
    const decisionKey = `settlement-decision.ui.${action.toLowerCase()}.${Date.now()}`;
    setState("working");
    try {
      await requestSandbox<SettlementRequestView>(
        `${commerceBaseUrl}/sandbox/live-commerce/settlement-requests/${encodeURIComponent(request.request_ref)}/decisions`,
        {
          method: "POST",
          headers: REVIEWER_HEADERS,
          body: JSON.stringify({
            decision_key: decisionKey,
            decision: action,
            reason: action === "APPROVE" ? "人工核对合成结算与原始支持记录一致" : "人工拒绝本次合成结算",
          }),
        },
      );
      setRequests(await loadRequests(commerceBaseUrl));
      setState("ready");
    } catch {
      setState("error");
    }
  }
}

async function loadRequests(baseUrl: string, signal?: AbortSignal): Promise<SettlementRequestView[]> {
  const response = await fetch(`${baseUrl}/sandbox/live-commerce/settlement-requests`, {
    cache: "no-store",
    headers: REVIEWER_HEADERS,
    signal,
  });
  if (!response.ok) throw new Error(`settlement queue rejected: ${response.status}`);
  const result = (await response.json()) as {
    requests: SettlementRequestView[];
    source: "SANDBOX_SYNTHETIC";
    fixture_only: true;
    external_effect: false;
  };
  if (
    result.source !== "SANDBOX_SYNTHETIC" ||
    result.fixture_only !== true ||
    result.external_effect !== false ||
    !Array.isArray(result.requests) ||
    result.requests.some((item) => !isSafeSettlement(item))
  ) {
    throw new Error("unsafe settlement queue evidence");
  }
  return result.requests;
}

async function requestSandbox<T extends SettlementRequestView>(url: string, init: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) throw new Error(`settlement request rejected: ${response.status}`);
  const result = (await response.json()) as T;
  if (!isSafeSettlement(result)) throw new Error("unsafe settlement evidence");
  return result;
}

function isSafeSettlement(value: SettlementRequestView): boolean {
  return value.source === "SANDBOX_SYNTHETIC"
    && value.fixture_only === true
    && value.external_effect === false
    && value.payment_state === "NOT_EXECUTED";
}

function settlementStateLabel(state: Exclude<SettlementState, "PENDING">): string {
  return state === "APPROVED" ? "已批准，等待外部付款系统（未执行）" : "已拒绝";
}

function formatAmount(amount: number, currency: SettlementRequestView["currency"]): string {
  return currency === "POINT" ? `${amount} 积分` : `¥${(amount / 100).toFixed(2)}`;
}

function isLocalUrl(value: string): boolean {
  try {
    return ["localhost", "127.0.0.1"].includes(new URL(value).hostname);
  } catch {
    return false;
  }
}
