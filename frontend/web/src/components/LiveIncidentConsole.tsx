import { useEffect, useState } from "react";

type Props = { incidentBaseUrl?: string };

type Incident = {
  report_ref: string;
  session_ref: string;
  reason: string;
  state: "PENDING" | "CONTINUED" | "HIDDEN" | "STOPPED";
  source: "SANDBOX_SYNTHETIC";
  fixture_only: true;
  external_effect: false;
  receipt?: { completed_components: string[]; external_effect: false } | null;
};

const HEADERS = {
  "Content-Type": "application/json",
  "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
  "X-Fixture-Only": "true",
  "X-Tenant-Id": "tenant.synthetic.alpha",
  "X-Family-Id": "family.synthetic.alpha",
  "X-Actor-Id": "actor.synthetic.moderator",
  "X-Actor-Role": "HUMAN_MODERATOR",
};

export function LiveIncidentConsole({ incidentBaseUrl }: Props) {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "missing" | "error">(
    incidentBaseUrl ? "loading" : "missing",
  );

  useEffect(() => {
    if (!incidentBaseUrl) return;
    void load();
  }, [incidentBaseUrl]);

  const pending = incidents.filter((incident) => incident.state === "PENDING");
  return (
    <section className="live-ops-shell" aria-labelledby="live-incident-heading">
      <header className="live-ops-heading">
        <div>
          <p className="live-kicker">TRUST · HUMAN CONTROL</p>
          <h2 id="live-incident-heading">直播安全事件</h2>
          <p>举报先进入人工队列；AI、专家和儿童不能执行隐藏或停播。</p>
        </div>
        <span>{pending.length} 条待处理</span>
      </header>
      {state === "missing" ? <p className="live-ops-state">安全事件服务暂未连接。</p> : null}
      {state === "loading" ? <p className="live-ops-state">正在读取举报队列…</p> : null}
      {state === "error" ? <p className="live-ops-state">举报队列不可用，禁止静默处置。</p> : null}
      {state === "ready" && pending.length === 0 ? (
        <div className="live-ops-empty"><strong>当前没有待处理举报</strong><p>新举报会在这里等待人工裁决。</p></div>
      ) : null}
      <div className="live-ops-list">
        {pending.map((incident) => (
          <article className="live-ops-card" key={incident.report_ref}>
            <div>
              <span>等待人工裁决</span>
              <strong>{incident.reason}</strong>
              <small>{incident.session_ref}</small>
            </div>
            <div className="live-ops-actions">
              <button type="button" onClick={() => void decide(incident, "CONTINUE")}>继续直播</button>
              <button type="button" onClick={() => void decide(incident, "HIDE")}>隐藏内容</button>
              <button className="live-ops-reject" type="button" onClick={() => void decide(incident, "STOP")}>人工停播</button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );

  async function load() {
    if (!incidentBaseUrl) return;
    try {
      const response = await fetch(`${incidentBaseUrl}/sandbox/live-incidents/reports`, {
        cache: "no-store",
        headers: HEADERS,
      });
      if (!response.ok) throw new Error("incident queue rejected");
      const payload = await response.json() as unknown;
      if (!Array.isArray(payload)) throw new Error("invalid incident queue");
      setIncidents(payload.map(parseIncident));
      setState("ready");
    } catch {
      setState("error");
    }
  }

  async function decide(incident: Incident, action: "CONTINUE" | "HIDE" | "STOP") {
    if (!incidentBaseUrl) return;
    try {
      const response = await fetch(
        `${incidentBaseUrl}/sandbox/live-incidents/reports/${incident.report_ref}/decisions`,
        {
          method: "POST",
          headers: HEADERS,
          body: JSON.stringify({
            decision_key: `decision:${incident.report_ref}:${action}`,
            action,
            reason: "人工复核并执行最小必要处置",
          }),
        },
      );
      if (!response.ok) throw new Error("incident decision rejected");
      const updated = parseIncident(await response.json());
      setIncidents((current) => current.map((item) => (
        item.report_ref === updated.report_ref ? updated : item
      )));
    } catch {
      setState("error");
    }
  }
}

function parseIncident(value: unknown): Incident {
  const record = typeof value === "object" && value !== null
    ? value as Record<string, unknown>
    : null;
  if (
    record === null ||
    typeof record.report_ref !== "string" ||
    typeof record.session_ref !== "string" ||
    typeof record.reason !== "string" ||
    !["PENDING", "CONTINUED", "HIDDEN", "STOPPED"].includes(String(record.state)) ||
    record.source !== "SANDBOX_SYNTHETIC" ||
    record.fixture_only !== true ||
    record.external_effect !== false
  ) throw new Error("unsafe incident response");
  return record as Incident;
}
