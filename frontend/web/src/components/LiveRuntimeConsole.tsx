import { useEffect, useState } from "react";

type Props = { observabilityBaseUrl?: string; sessionRef?: string };
type ComponentState = "UP" | "DOWN" | "UNSAFE";
type RuntimeComponent = {
  component: "media" | "interaction" | "replay" | "commerce";
  state: ComponentState;
  latency_ms: number;
  detail: string;
  external_effect: false;
};
type RuntimeSnapshot = {
  overall: "READY" | "DEGRADED";
  checked_at: string;
  components: RuntimeComponent[];
  source: "SANDBOX_SYNTHETIC";
  fixture_only: true;
  external_effect: false;
};
type SloSnapshot = {
  session_ref: string;
  sample_count: number;
  startup_success: number | null;
  first_frame_p95_ms: number | null;
  stall_ratio: number | null;
  interaction_latency_p95_ms: number | null;
  recovery_p95_ms: number | null;
  error_budget: number;
  recommendation: "GREEN" | "DEGRADED" | "STOP";
  reasons: string[];
  human_review_required: boolean;
  automatic_stop_issued: false;
  source: "SANDBOX_SYNTHETIC";
  fixture_only: true;
  external_effect: false;
};

const OPERATOR_HEADERS = {
  "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
  "X-Fixture-Only": "true",
  "X-Tenant-Id": "tenant.synthetic.alpha",
  "X-Family-Id": "family.synthetic.alpha",
  "X-Actor-Id": "actor.synthetic.operator",
  "X-Actor-Role": "LIVE_OPERATOR",
};
const RUNTIME_COMPONENTS = ["media", "interaction", "replay", "commerce"] as const;

export function LiveRuntimeConsole({
  observabilityBaseUrl,
  sessionRef = "live.synthetic.control.1",
}: Props) {
  const [snapshot, setSnapshot] = useState<RuntimeSnapshot | null>(null);
  const [slo, setSlo] = useState<SloSnapshot | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "missing" | "error">(
    observabilityBaseUrl ? "loading" : "missing",
  );

  useEffect(() => {
    if (!observabilityBaseUrl || !isLocalUrl(observabilityBaseUrl)) return;
    const controller = new AbortController();
    void loadRuntimeEvidence(observabilityBaseUrl, sessionRef, controller.signal)
      .then((result) => {
        setSnapshot(result.snapshot);
        setSlo(result.slo);
        setState("ready");
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) setState("error");
      });
    return () => controller.abort();
  }, [observabilityBaseUrl, sessionRef]);

  return (
    <section className="live-ops-shell" aria-labelledby="live-runtime-heading">
      <header className="live-ops-heading">
        <div>
          <p className="live-kicker">Live SRE · 只读故障快照</p>
          <h2 id="live-runtime-heading">直播运行状态</h2>
          <p>媒体、互动、回放或交易任一异常都会显示降级，不会静默伪装成正常。</p>
        </div>
        <span>{snapshot?.overall ?? "UNKNOWN"}</span>
      </header>

      {state === "loading" ? <p className="live-ops-state">正在检查直播依赖…</p> : null}
      {state === "missing" ? <p className="live-ops-state">运行观测服务暂未连接。</p> : null}
      {state === "error" ? <p className="live-ops-state">无法取得可信运行快照，按降级处理。</p> : null}
      {snapshot ? (
        <>
          <div className="live-ops-list" aria-label="直播依赖状态">
            {snapshot.components.map((component) => (
              <article className="live-ops-card" key={component.component}>
                <div>
                  <span>{component.state}</span>
                  <strong>{componentLabel(component.component)}</strong>
                  <small>{component.latency_ms} ms · {component.detail}</small>
                </div>
              </article>
            ))}
          </div>
          {slo ? <SloPanel slo={slo} /> : null}
          <button type="button" onClick={() => void refresh()}>重新检查运行状态</button>
        </>
      ) : null}
    </section>
  );

  async function refresh() {
    if (!observabilityBaseUrl || !isLocalUrl(observabilityBaseUrl)) return;
    setState("loading");
    try {
      const evidence = await loadRuntimeEvidence(observabilityBaseUrl, sessionRef);
      setSnapshot(evidence.snapshot);
      setSlo(evidence.slo);
      setState("ready");
    } catch {
      setSnapshot(null);
      setSlo(null);
      setState("error");
    }
  }
}

function SloPanel({ slo }: { slo: SloSnapshot }) {
  const metrics = [
    ["首帧 P95", formatMilliseconds(slo.first_frame_p95_ms)],
    ["卡顿率", formatPercent(slo.stall_ratio)],
    ["互动延迟 P95", formatMilliseconds(slo.interaction_latency_p95_ms)],
    ["恢复时间 P95", formatMilliseconds(slo.recovery_p95_ms)],
    ["错误预算", formatPercent(slo.error_budget)],
  ];
  return (
    <section className="live-slo-panel" aria-label="本场直播质量目标">
      <div className="live-slo-summary">
        <div>
          <small>本场质量判断 · {slo.sample_count} 个样本</small>
          <strong>{slo.recommendation}</strong>
        </div>
        <p>
          {slo.recommendation === "STOP"
            ? "指标要求人工止损确认；系统没有自动停播。"
            : slo.reasons[0] ?? "当前指标处于沙盒目标范围。"}
        </p>
      </div>
      <div className="live-slo-metrics">
        {metrics.map(([label, value]) => (
          <div key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}

async function loadRuntimeEvidence(
  baseUrl: string,
  sessionRef: string,
  signal?: AbortSignal,
): Promise<{ snapshot: RuntimeSnapshot; slo: SloSnapshot }> {
  const [snapshot, slo] = await Promise.all([
    loadSnapshot(baseUrl, signal),
    loadSlo(baseUrl, sessionRef, signal),
  ]);
  return { snapshot, slo };
}

async function loadSnapshot(baseUrl: string, signal?: AbortSignal): Promise<RuntimeSnapshot> {
  const response = await fetch(`${baseUrl}/sandbox/live-ops/runtime-snapshot`, {
    cache: "no-store",
    headers: OPERATOR_HEADERS,
    signal,
  });
  if (!response.ok) throw new Error(`runtime snapshot rejected: ${response.status}`);
  const result = (await response.json()) as RuntimeSnapshot;
  if (
    result.source !== "SANDBOX_SYNTHETIC" ||
    result.fixture_only !== true ||
    result.external_effect !== false ||
    !["READY", "DEGRADED"].includes(result.overall) ||
    typeof result.checked_at !== "string" ||
    !Array.isArray(result.components) ||
    result.components.length !== RUNTIME_COMPONENTS.length ||
    new Set(result.components.map((item) => item.component)).size !== RUNTIME_COMPONENTS.length ||
    result.components.some(
      (item) =>
        !RUNTIME_COMPONENTS.includes(item.component) ||
        !["UP", "DOWN", "UNSAFE"].includes(item.state) ||
        !Number.isFinite(item.latency_ms) ||
        item.latency_ms < 0 ||
        typeof item.detail !== "string" ||
        item.external_effect !== false,
    )
  ) {
    throw new Error("unsafe runtime snapshot");
  }
  return result;
}

async function loadSlo(
  baseUrl: string,
  sessionRef: string,
  signal?: AbortSignal,
): Promise<SloSnapshot> {
  const response = await fetch(
    `${baseUrl}/sandbox/live-ops/sessions/${encodeURIComponent(sessionRef)}/slo`,
    { cache: "no-store", headers: OPERATOR_HEADERS, signal },
  );
  if (!response.ok) throw new Error(`SLO snapshot rejected: ${response.status}`);
  const result = (await response.json()) as SloSnapshot;
  const nullableMetrics = [
    result.startup_success,
    result.first_frame_p95_ms,
    result.stall_ratio,
    result.interaction_latency_p95_ms,
    result.recovery_p95_ms,
  ];
  if (
    result.session_ref !== sessionRef ||
    result.source !== "SANDBOX_SYNTHETIC" ||
    result.fixture_only !== true ||
    result.external_effect !== false ||
    result.automatic_stop_issued !== false ||
    !["GREEN", "DEGRADED", "STOP"].includes(result.recommendation) ||
    !Number.isInteger(result.sample_count) ||
    result.sample_count < 0 ||
    !Number.isFinite(result.error_budget) ||
    result.error_budget < 0 ||
    result.error_budget > 1 ||
    !Array.isArray(result.reasons) ||
    result.reasons.some((reason) => typeof reason !== "string") ||
    nullableMetrics.some((metric) => metric !== null && (!Number.isFinite(metric) || metric < 0)) ||
    (result.recommendation === "STOP" && result.human_review_required !== true)
  ) {
    throw new Error("unsafe SLO snapshot");
  }
  return result;
}

function formatMilliseconds(value: number | null): string {
  return value === null ? "无可信样本" : `${Math.round(value)} ms`;
}

function formatPercent(value: number | null): string {
  return value === null ? "无可信样本" : `${(value * 100).toFixed(1)}%`;
}

function componentLabel(component: RuntimeComponent["component"]): string {
  return {
    media: "视频媒体",
    interaction: "成人互动与审核",
    replay: "录制回放",
    commerce: "交易与权益",
  }[component];
}

function isLocalUrl(value: string): boolean {
  try {
    return ["localhost", "127.0.0.1"].includes(new URL(value).hostname);
  } catch {
    return false;
  }
}
