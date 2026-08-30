import { useState } from "react";
import type { LiveRecord, MediaPlaybackState } from "../live/liveCatalog";

type Props = {
  record: LiveRecord;
  onBack: () => void;
};

export function LiveDetailPage({ record, onBack }: Props) {
  const playback = record.playback;
  const [surfaceState, setSurfaceState] = useState<"WAITING_AUTHORIZATION" | "LOADING" | MediaPlaybackState | "FAILED">(
    playback?.state ?? "WAITING_AUTHORIZATION",
  );
  const canRenderVideo = playback?.source === "synthetic" && playback.fixture_only && playback.state === "LIVE" && isLocalPlaybackUrl(playback.playback_url);
  const playbackMessage = getPlaybackMessage(surfaceState);

  return (
    <article className="live-detail-page" aria-labelledby="live-detail-heading">
      <div className="live-detail-header">
        <div>
          <p className="live-kicker">H-LIVE-01 · 只读详情</p>
          <h3 id="live-detail-heading">{record.title}</h3>
        </div>
        <span className="live-status-badge">{record.status}</span>
      </div>
      <section className="live-video-container" aria-labelledby="live-video-heading" data-playback-state={surfaceState}>
        {canRenderVideo ? (
          <div className="live-video-frame live-video-authorized">
            <h4 id="live-video-heading" className="visually-hidden">视频播放区域</h4>
            <video
              aria-label="小橘灯合成视频播放区域"
              controls
              playsInline
              preload="metadata"
              src={playback.playback_url}
              onError={() => setSurfaceState("FAILED")}
              onLoadStart={() => setSurfaceState("LOADING")}
              onPlaying={() => setSurfaceState("LIVE")}
              onStalled={() => setSurfaceState("DISCONNECTED")}
              onWaiting={() => setSurfaceState("DISCONNECTED")}
            />
            <div className="live-video-caption" role="status" aria-live="polite">
              <span className="live-readonly">SANDBOX_SYNTHETIC · FIXTURE_ONLY</span>
              <span className="live-video-state">{surfaceState}</span>
              <p>{playbackMessage}</p>
            </div>
          </div>
        ) : (
          <div className="live-video-frame" role="status">
            <span className="live-readonly">PLAYER SURFACE · FAIL-CLOSED</span>
            <h4 id="live-video-heading">{surfaceState === "WAITING_AUTHORIZATION" ? "视频暂不可用" : playbackMessage}</h4>
            <p>{playbackMessage}</p>
            <span className="live-video-state">{surfaceState}</span>
          </div>
        )}
      </section>
      <dl className="live-detail-grid">
        <div><dt>主讲人</dt><dd>{record.speaker}</dd></div>
        <div><dt>适用范围</dt><dd>{record.applicable_scope}</dd></div>
        <div><dt>开始时间</dt><dd>{record.starts_at}</dd></div>
        <div><dt>结束时间</dt><dd>{record.ends_at}</dd></div>
        <div><dt>审核状态</dt><dd>{record.approval_status}</dd></div>
        <div><dt>有效期</dt><dd>{record.expiry_state}</dd></div>
        <div><dt>AudienceScope</dt><dd>{record.audience_scope}</dd></div>
        <div><dt>收藏</dt><dd>{record.capabilities.favorite} · 不可用</dd></div>
        <div><dt>回看</dt><dd>{record.capabilities.replay} · 不可用</dd></div>
        <div><dt>审核引用</dt><dd>{record.review_ref}</dd></div>
        <div><dt>版本</dt><dd>{record.version}</dd></div>
        <div><dt>family visibility</dt><dd>{record.family_visibility}</dd></div>
        <div><dt>as_of</dt><dd>{record.as_of}</dd></div>
        <div><dt>source</dt><dd>{record.source}</dd></div>
        <div><dt>fixture_only</dt><dd>{record.fixture_only ? "true · DEV_ONLY" : "false"}</dd></div>
      </dl>
      <p className="live-detail-note">本页仅展示审核过的只读字段，不提供互动或状态变更。</p>
      <button className="live-back-button" type="button" onClick={onBack}>
        返回直播发现
      </button>
    </article>
  );
}

function isLocalPlaybackUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return ["localhost", "127.0.0.1"].includes(url.hostname) && ["http:", "https:"].includes(url.protocol);
  } catch {
    return false;
  }
}

function getPlaybackMessage(state: "WAITING_AUTHORIZATION" | "LOADING" | MediaPlaybackState | "FAILED"): string {
  switch (state) {
    case "WAITING_AUTHORIZATION":
      return "等待授权后才可评估播放能力；当前不会加载媒体。";
    case "LOADING":
      return "视频正在加载。";
    case "LIVE":
      return "视频播放区域已获得 Sandbox capability；不会自动播放。";
    case "DISCONNECTED":
      return "视频连接暂时中断，播放已暂停。";
    case "RESTARTED":
      return "视频连接已重启，等待继续播放。";
    case "ENDED":
      return "视频已结束，当前不提供回看。";
    case "STOPPED":
      return "视频已停止。";
    case "REVOKED":
      return "视频授权已撤回，播放已停止。";
    case "FAILED":
      return "视频暂时不可用，页面保持安全停止。";
  }
}
