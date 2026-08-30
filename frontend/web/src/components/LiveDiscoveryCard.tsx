import type { LiveRecord } from "../live/liveCatalog";

type Props = {
  record: LiveRecord;
  onOpenDetail?: () => void;
};

export function LiveDiscoveryCard({ record, onOpenDetail }: Props) {
  const runtimeStatus = record.section === "live-now" ? "LIVE" : record.section === "upcoming" ? "SCHEDULED" : "ENDED";
  const mediaReady = record.playback?.state === "LIVE";

  return (
    <article className="live-discovery-card">
      <div className={`live-card-visual${mediaReady ? " live-card-visual-ready" : ""}`} role="img" aria-label={mediaReady ? "视频播放区域已授权" : "视频暂不可用 · 等待授权"}>
        <span className="live-visual-badge">{mediaReady ? "MEDIA_READY" : "NO_MEDIA"}</span>
        <strong>{mediaReady ? "视频播放区域已授权" : "视频暂不可用"}</strong>
        <span>{mediaReady ? "PLAYBACK_AUTHORIZED" : "WAITING_AUTHORIZATION"}</span>
      </div>
      <div className="live-card-topline">
        <span className="live-pill">专家直播</span>
        <span className="live-readonly">只读信息</span>
        <span className={`live-runtime-chip live-runtime-${runtimeStatus.toLowerCase()}`}>{runtimeStatus}</span>
        <span className="live-status-chip">{record.approval_status} · {record.expiry_state}</span>
        <span className="live-audit-chip">{record.review_ref}</span>
        <span className="live-sandbox-mark">DEV_ONLY</span>
      </div>
      <h3>{record.title}</h3>
      <div className="live-expert-line">
        <span className="live-expert-avatar" aria-hidden="true">小</span>
        <span className="live-card-speaker">{record.speaker}</span>
      </div>
      <div className="live-problem-tags" aria-label="家庭问题标签">
        {record.problem_tags.map((tag) => <span key={tag}>#{tag}</span>)}
      </div>
      <dl className="live-card-summary">
        <div>
          <dt>适用范围</dt>
          <dd>{record.applicable_scope}</dd>
        </div>
        <div>
          <dt>时间</dt>
          <dd>{record.starts_at} — {record.ends_at}</dd>
        </div>
        <div>
          <dt>审核状态</dt>
          <dd>{record.approval_status} · {record.expiry_state}</dd>
        </div>
        <div>
          <dt>适用家庭</dt>
          <dd>{record.audience_scope} · {record.family_visibility}</dd>
        </div>
      </dl>
      {onOpenDetail ? (
        <button className="live-detail-button" type="button" onClick={onOpenDetail}>
          查看直播详情
        </button>
      ) : (
        <span className="live-locked-action">回看受限 · LOCKED</span>
      )}
    </article>
  );
}
