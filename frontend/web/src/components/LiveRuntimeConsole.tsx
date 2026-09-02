import { useEffect, useState } from "react";

type Props = { observabilityBaseUrl?: string };
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

const OPERATOR_HEADERS = {
  "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
  "X-Fixture-Only": "true",
  "X-Tenant-Id": "tenant.synthetic.alpha",
  "X-Family-Id": "family.synthetic.alpha",
  "X-Actor-Id": "actor.synthetic.operator",
  "X-Actor-Role": "LIVE_OPERATOR",
};
const RUNTIME_COMPONENTS = ["media", "interaction", "replay", "commerce"] as const;

export function LiveRuntimeConsole({ observabilityBaseUrl }: Props) {
  const [snapshot, setSnapshot] = useState<RuntimeSnapshot | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "missing" | "error">(
    observabilityBaseUrl ? "loading" : "missing",
  );

  useEffect(() => {
    if (!observabilityBaseUrl || !isLocalUrl(observabilityBaseUrl)) return;
    const controller = new AbortController();
    void loadSnapshot(observabilityBaseUrl, controller.signal)
      .then((result) => {
        setSnapshot(result);
        setState("ready");
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) setState("error");
      });
    return () => controller.abort();
  }, [observabilityBaseUrl]);

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
          <button type="button" onClick={() => void refresh()}>重新检查运行状态</button>
        </>
      ) : null}
    </section>
  );

  async function refresh() {
    if (!observabilityBaseUrl || !isLocalUrl(observabilityBaseUrl)) return;
    setState("loading");
    try {
      setSnapshot(await loadSnapshot(observabilityBaseUrl));
      setState("ready");
    } catch {
      setSnapshot(null);
      setState("error");
    }
  }
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
