import { useEffect, useState } from "react";

type Props = { controlBaseUrl?: string };
type Session = {
  session_ref: string;
  title: string;
  speaker: string;
  status: "SCHEDULED" | "LIVE" | "ENDED" | "WITHDRAWN";
  approval_status: "DRAFT" | "APPROVED" | "REJECTED" | "WITHDRAWN";
  version: string;
  source: "SANDBOX_SYNTHETIC";
  fixture_only: true;
  external_effect: false;
  audit_mode: "SANDBOX_RECEIPT_ONLY";
};

export function LiveSessionControlConsole({ controlBaseUrl }: Props) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "missing" | "error">(
    controlBaseUrl ? "loading" : "missing",
  );
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!controlBaseUrl) return;
    const controller = new AbortController();
    void loadSessions(controlBaseUrl, controller.signal)
      .then((items) => {
        setSessions(items);
        setState("ready");
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) setState("error");
      });
    return () => controller.abort();
  }, [controlBaseUrl]);

  return (
    <section className="live-ops-shell" aria-labelledby="live-control-heading">
      <header className="live-ops-heading">
        <div>
          <p className="live-kicker">Creator + Content Safety + Live Ops</p>
          <h2 id="live-control-heading">直播场次控制台</h2>
          <p>专家创建草稿，人工审核后才能开播；停止后家庭首页立即不可见。</p>
        </div>
        <span>SANDBOX_SYNTHETIC</span>
      </header>

      {state === "loading" ? <p className="live-ops-state">正在读取场次…</p> : null}
      {state === "missing" ? <p className="live-ops-state">Control Plane 暂未连接。</p> : null}
      {state === "error" ? <p className="live-ops-state">场次控制面不可用，所有操作已停止。</p> : null}
      {state === "ready" ? (
        <>
          <div className="live-ops-list" aria-label="直播场次列表">
            {sessions.map((session) => (
              <article
                className="live-ops-card"
                aria-label={`直播场次 ${session.title}`}
                key={session.session_ref}
              >
                <div>
                  <span>{session.approval_status} · {session.status}</span>
                  <strong>{session.title}</strong>
                  <small>{session.speaker} · {session.version}</small>
                </div>
                <div className="live-ops-actions">
                  {session.approval_status === "DRAFT" ? (
                    <button type="button" onClick={() => void approve(session)}>
                      人工审核通过
                    </button>
                  ) : null}
                  {session.approval_status === "APPROVED" && session.status === "SCHEDULED" ? (
                    <button type="button" onClick={() => void goLive(session)}>
                      开始直播
                    </button>
                  ) : null}
                  {session.status === "LIVE" ? (
                    <button
                      className="live-ops-reject"
                      type="button"
                      onClick={() => void withdraw(session)}
                    >
                      人工停止直播
                    </button>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
          <div className="live-ops-state">
            <button type="button" onClick={() => void createSession()}>创建新的演示场次</button>
            {message ? <p role="status">{message}</p> : null}
          </div>
        </>
      ) : null}
    </section>
  );

  async function createSession() {
    if (!controlBaseUrl) return;
    setMessage("正在创建场次…");
    const sequence = Date.now();
    try {
      const now = Date.now();
      const session = await requestSession(
        `${controlBaseUrl}/sandbox/live-control/sessions`,
        "CREATOR",
        {
          session_ref: `live.synthetic.creator.${sequence}`,
          idempotency_key: `create:${sequence}`,
          title: "小橘灯：把冲突变成一次共同练习",
          speaker: "合成专家",
          expert_summary: "从具体家庭场景出发，由成人一起练习倾听与回应。",
          applicable_scope: "成年家长与照护者",
          problem_tags: ["家庭沟通", "冲突复盘"],
          starts_at: new Date(now - 60_000).toISOString(),
          ends_at: new Date(now + 3_600_000).toISOString(),
          audience_scope: "FAMILY",
        },
      );
      setSessions((current) => [session, ...current]);
      setMessage("场次草稿已创建，等待人工内容审核。");
    } catch {
      setMessage("创建失败，未产生直播场次。");
    }
  }

  async function approve(session: Session) {
    await mutate(
      session,
      "CONTENT_REVIEWER",
      "review",
      {
        decision_key: `approve:${session.session_ref}`,
        action: "APPROVE",
        reason: "人工确认内容适合成年家庭成员",
        review_ref: `review:${session.session_ref}`,
      },
      "人工审核完成，可以由运营开播。",
    );
  }

  async function goLive(session: Session) {
    await mutate(
      session,
      "LIVE_OPERATOR",
      "lifecycle",
      {
        action_key: `start:${session.session_ref}`,
        action: "GO_LIVE",
        reason: "人工确认场次与合成媒体已准备",
      },
      "直播已开始，符合范围的家庭可以发现。",
    );
  }

  async function withdraw(session: Session) {
    await mutate(
      session,
      "LIVE_OPERATOR",
      "lifecycle",
      {
        action_key: `stop:${session.session_ref}`,
        action: "WITHDRAW",
        reason: "人工停止直播",
      },
      "直播已人工停止，家庭入口已撤回。",
    );
  }

  async function mutate(
    session: Session,
    role: string,
    action: string,
    payload: Record<string, unknown>,
    successMessage: string,
  ) {
    if (!controlBaseUrl) return;
    setMessage("正在执行人工操作…");
    try {
      const updated = await requestSession(
        `${controlBaseUrl}/sandbox/live-control/sessions/${session.session_ref}/${action}`,
        role,
        payload,
      );
      setSessions((current) => current.map((item) => (
        item.session_ref === updated.session_ref ? updated : item
      )));
      setMessage(successMessage);
    } catch {
      setMessage("操作失败，场次状态没有改变。");
    }
  }
}

async function loadSessions(baseUrl: string, signal?: AbortSignal): Promise<Session[]> {
  const response = await fetch(`${baseUrl}/sandbox/live-control/operator/sessions`, {
    cache: "no-store",
    headers: actorHeaders("CREATOR"),
    signal,
  });
  if (!response.ok) throw new Error(`control listing rejected: ${response.status}`);
  const payload = await response.json() as unknown;
  if (!Array.isArray(payload)) throw new Error("invalid control listing");
  return payload.map(parseSession);
}

async function requestSession(
  url: string,
  role: string,
  payload: Record<string, unknown>,
): Promise<Session> {
  const response = await fetch(url, {
    method: "POST",
    headers: { ...actorHeaders(role), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) throw new Error(`control mutation rejected: ${response.status}`);
  return parseSession(await response.json());
}

function parseSession(value: unknown): Session {
  const record = isRecord(value) ? value : null;
  if (
    record === null ||
    typeof record.session_ref !== "string" ||
    typeof record.title !== "string" ||
    typeof record.speaker !== "string" ||
    typeof record.version !== "string" ||
    !["SCHEDULED", "LIVE", "ENDED", "WITHDRAWN"].includes(String(record.status)) ||
    !["DRAFT", "APPROVED", "REJECTED", "WITHDRAWN"].includes(
      String(record.approval_status),
    ) ||
    record.source !== "SANDBOX_SYNTHETIC" ||
    record.fixture_only !== true ||
    record.external_effect !== false ||
    record.audit_mode !== "SANDBOX_RECEIPT_ONLY"
  ) throw new Error("unsafe control session");
  return record as Session;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function actorHeaders(role: string): Record<string, string> {
  return {
    "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
    "X-Fixture-Only": "true",
    "X-Tenant-Id": "tenant.synthetic.alpha",
    "X-Family-Id": "family.synthetic.alpha",
    "X-Actor-Id": `actor.synthetic.${role.toLowerCase()}`,
    "X-Actor-Role": role,
  };
}
