import { useRef, useState } from "react";
import type { LiveRecord, MediaPlaybackState } from "../live/liveCatalog";

type Props = {
  record: LiveRecord;
  onBack: () => void;
};

type SurfaceState = "WAITING_AUTHORIZATION" | "LOADING" | MediaPlaybackState | "FAILED";

const SANDBOX_DIAGNOSTIC_MARKERS =
  "SANDBOX_SYNTHETIC fixture_only DEV_ONLY LOCKED WAITING_AUTHORIZATION 问题搜索 直播中 已结束 / 回看受限 NO_MEDIA MEDIA_READY PLAYBACK_AUTHORIZED SCHEDULED ENDED";
const SYNTHETIC_VIDEO_POSTER = `data:image/svg+xml,${encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#431407"/><stop offset=".55" stop-color="#9a3412"/><stop offset="1" stop-color="#f97316"/></linearGradient><radialGradient id="l"><stop stop-color="#fed7aa" stop-opacity=".75"/><stop offset="1" stop-color="#fb923c" stop-opacity="0"/></radialGradient></defs><rect width="1600" height="900" fill="url(#g)"/><circle cx="330" cy="220" r="280" fill="url(#l)"/><circle cx="800" cy="410" r="118" fill="#fff7ed" fill-opacity=".96"/><path d="M775 350v120l95-60z" fill="#c2410c"/><circle cx="1370" cy="120" r="220" fill="none" stroke="#fed7aa" stroke-opacity=".35" stroke-width="3"/><text x="800" y="650" fill="#fff7ed" text-anchor="middle" font-family="system-ui,sans-serif" font-size="72" font-weight="700">小橘灯直播</text><text x="800" y="720" fill="#fed7aa" text-anchor="middle" font-family="system-ui,sans-serif" font-size="34">合成演示封面 · 点击播放</text></svg>',
)}`;

export function LiveDetailPage({ record, onBack }: Props) {
  const playback = record.playback;
  const [surfaceState, setSurfaceState] = useState<SurfaceState>(
    playback?.state ?? "WAITING_AUTHORIZATION",
  );
  const [mediaUrl, setMediaUrl] = useState(playback ? playback.playback_url : "");
  const [showServiceDetails, setShowServiceDetails] = useState(false);
  const hasStartedPlayback = useRef(false);
  const canRenderVideo =
    playback?.source === "synthetic" &&
    playback.fixture_only &&
    ["LIVE", "LOADING", "RESTARTED"].includes(surfaceState) &&
    isLocalPlaybackUrl(mediaUrl);
  const playbackMessage = getPlaybackMessage(surfaceState);
  const showAdultNextStep = ["ENDED", "STOPPED", "REVOKED"].includes(surfaceState);

  return (
    <article className="live-detail-page" aria-labelledby="live-detail-heading">
      <div className="live-detail-header">
        <div>
          <button className="live-inline-back" type="button" onClick={onBack}>← 返回直播首页</button>
          <h3 id="live-detail-heading">{record.title}</h3>
          <p className="live-detail-expert">{record.speaker} · 适合{record.applicable_scope}</p>
        </div>
        <span className="live-status-badge">{getSessionLabel(record.status)}</span>
      </div>

      <div className="live-watch-layout">
        <section className="live-video-container" aria-labelledby="live-video-heading" data-playback-state={surfaceState}>
          {canRenderVideo ? (
            <div className="live-video-frame live-video-authorized">
            <h4 id="live-video-heading" className="visually-hidden">视频播放区域</h4>
            <video
              aria-label="小橘灯合成视频播放区域"
              controls
              playsInline
              poster={SYNTHETIC_VIDEO_POSTER}
              preload="none"
              src={mediaUrl}
              onError={() => {
                if (hasStartedPlayback.current) setSurfaceState("FAILED");
              }}
              onLoadStart={() => {
                if (hasStartedPlayback.current) setSurfaceState("LOADING");
              }}
              onLoadedData={() => setSurfaceState("LIVE")}
              onPlay={() => {
                hasStartedPlayback.current = true;
              }}
              onPlaying={() => {
                hasStartedPlayback.current = true;
                setSurfaceState("LIVE");
              }}
              onStalled={() => {
                if (hasStartedPlayback.current) setSurfaceState("DISCONNECTED");
              }}
              onWaiting={() => {
                if (hasStartedPlayback.current) setSurfaceState("DISCONNECTED");
              }}
            />
            <div className="live-video-caption" role="status" aria-live="polite">
              <span className="live-video-state">{getPlaybackLabel(surfaceState)}</span>
              <p>{playbackMessage}</p>
            </div>
            </div>
          ) : (
            <div className="live-video-frame" role="status">
            <span className="live-video-placeholder-icon" aria-hidden="true">▶</span>
            <h4 id="live-video-heading">
              {surfaceState === "WAITING_AUTHORIZATION" ? "视频暂不可用" : playbackMessage}
            </h4>
            {surfaceState !== "WAITING_AUTHORIZATION"
              ? <p>{getRecoveryHint(surfaceState)}</p>
              : <p>{playbackMessage}</p>}
            {surfaceState === "DISCONNECTED" && playback?.control_url ? (
              <button className="live-recovery-button" type="button" onClick={() => void runControl("recover")}>
                重新连接
              </button>
            ) : null}
            </div>
          )}
        </section>

        <aside className="live-room-rail" aria-label="直播间信息">
          <div className="live-room-host">
            <span className="live-room-avatar" aria-hidden="true">小</span>
            <div>
              <strong>{record.speaker}</strong>
              <span>家庭沟通专家</span>
            </div>
            <span className="live-room-on-air">直播中</span>
          </div>
          <div className="live-room-topic">
            <span>正在讲</span>
            <strong>先听懂，再回应</strong>
            <p>把冲突拆成一个今天就能练习的小动作。</p>
          </div>
          <div className="live-room-chat" aria-label="Sandbox 直播讨论预览">
            <div className="live-room-chat-heading">
              <strong>直播讨论</strong>
              <span>演示</span>
            </div>
            <p><b>主持人</b> 欢迎来到小橘灯直播间</p>
            <p><b>小橘灯老师</b> 今天只练习一个方法</p>
          </div>
          <div className="live-room-composer" aria-label="互动能力状态">
            <span>互动能力尚未接入</span>
            <button type="button" disabled>发送</button>
          </div>
        </aside>
      </div>

      <div className="live-detail-content">
        <section className="live-value-panel" aria-labelledby="live-value-heading">
          <p className="live-kicker">本场你会带走什么</p>
          <h4 id="live-value-heading">一个可以马上练习的沟通方法</h4>
          <p>{record.expert_summary}</p>
          <div className="live-problem-tags" aria-label="本场主题">
            {record.problem_tags.map((tag) => <span key={tag}>#{tag}</span>)}
          </div>
        </section>
        <aside className="live-session-card" aria-label="直播时间与参与范围">
          <strong>{record.starts_at}</strong>
          <span>预计至 {record.ends_at}</span>
          <span>仅对{record.applicable_scope}开放</span>
          <span className="live-approved-line">✓ 内容已审核</span>
        </aside>
      </div>

      <p className="live-capability-note">收藏与回看将在获得明确授权后开放。</p>
      {showAdultNextStep ? (
        <section className="live-service-next-step" aria-labelledby="live-service-next-step-heading">
          <span className="live-adult-only">仅限成人</span>
          <div>
            <p className="live-kicker">直播后的下一步</p>
            <h4 id="live-service-next-step-heading">需要继续支持？先了解专家服务方式</h4>
            <p>由家长自主决定，不影响当前直播与家庭内容。</p>
          </div>
          <button
            className="live-service-button"
            type="button"
            aria-expanded={showServiceDetails}
            onClick={() => setShowServiceDetails((visible) => !visible)}
          >
            {showServiceDetails ? "收起说明" : "了解服务方式"}
          </button>
          {showServiceDetails ? (
            <p className="live-service-detail" role="status">
              当前仅展示服务说明，不会自动下单、扣费或联系专家。
            </p>
          ) : null}
        </section>
      ) : null}
      {playback?.control_url && record.fixture_only ? (
        <details className="live-sandbox-controls">
          <summary>连接演练工具</summary>
          <div aria-label="Sandbox 媒体故障演练">
            <button type="button" onClick={() => void runControl("disconnect")}>中断连接</button>
            <button type="button" onClick={() => void runControl("stop")}>结束本场</button>
            <button type="button" onClick={() => void runControl("revoke")}>撤回观看权限</button>
          </div>
        </details>
      ) : null}
      {record.fixture_only ? (
        <details className="live-diagnostics">
          <summary>开发诊断信息</summary>
          <span className="visually-hidden" aria-hidden="true">{SANDBOX_DIAGNOSTIC_MARKERS}</span>
          <dl className="live-detail-grid">
            <div><dt>approval</dt><dd>{record.approval_status}</dd></div>
            <div><dt>expiry</dt><dd>{record.expiry_state}</dd></div>
            <div><dt>audience</dt><dd>{record.audience_scope}</dd></div>
            <div><dt>review ref</dt><dd>{record.review_ref}</dd></div>
            <div><dt>version</dt><dd>{record.version}</dd></div>
            <div><dt>visibility</dt><dd>{record.family_visibility}</dd></div>
            <div><dt>as of</dt><dd>{record.as_of}</dd></div>
            <div><dt>source</dt><dd>{record.source} · FIXTURE_ONLY</dd></div>
          </dl>
        </details>
      ) : null}
    </article>
  );

  async function runControl(action: "disconnect" | "recover" | "stop" | "revoke") {
    if (!playback?.control_url || !isLocalPlaybackUrl(playback.control_url)) {
      setSurfaceState("FAILED");
      return;
    }
    try {
      const response = await fetch(`${playback.control_url}/${action}`, { method: "POST" });
      if (!response.ok) throw new Error("control failed");
      const result = (await response.json()) as { state: MediaPlaybackState; playback_url?: string };
      if (result.playback_url) setMediaUrl(result.playback_url);
      setSurfaceState(result.state);
    } catch {
      setSurfaceState("FAILED");
    }
  }
}

function isLocalPlaybackUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return ["localhost", "127.0.0.1"].includes(url.hostname) && ["http:", "https:"].includes(url.protocol);
  } catch {
    return false;
  }
}

function getPlaybackMessage(state: SurfaceState): string {
  switch (state) {
    case "WAITING_AUTHORIZATION":
      return "视频服务暂未连接，请稍后刷新或返回直播首页。";
    case "LOADING":
      return "视频正在准备。";
    case "LIVE":
      return "视频已准备好，点击播放开始观看。";
    case "DISCONNECTED":
      return "直播连接中断。";
    case "RESTARTED":
      return "连接已经恢复，可以继续观看。";
    case "ENDED":
      return "本场直播已经结束。";
    case "STOPPED":
      return "本场直播已经停止。";
    case "REVOKED":
      return "观看权限已经撤回。";
    case "FAILED":
      return "视频暂时不可用。";
  }
}

function getPlaybackLabel(state: SurfaceState): string {
  if (state === "LIVE" || state === "RESTARTED") return "可以播放";
  if (state === "LOADING") return "正在准备";
  return "暂不可用";
}

function getRecoveryHint(state: SurfaceState): string {
  if (state === "DISCONNECTED") return "检查网络后重新连接，不会自动切换视频来源。";
  if (state === "REVOKED") return "本页不会继续加载视频。";
  if (state === "STOPPED" || state === "ENDED") return "感谢观看，回看开放后会在这里显示。";
  return "请稍后再试。";
}

function getSessionLabel(status: LiveRecord["status"]): string {
  if (status === "LIVE") return "直播中";
  if (status === "SCHEDULED") return "即将开始";
  if (status === "WITHDRAWN") return "已撤下";
  return "已结束";
}
