import type { LiveRecord } from "../live/liveCatalog";

type Props = {
  record: LiveRecord;
  onOpenDetail?: () => void;
};

export function LiveDiscoveryCard({ record, onOpenDetail }: Props) {
  const runtimeLabel = record.section === "live-now" ? "正在直播" : record.section === "upcoming" ? "直播预告" : "本场已结束";
  const mediaReady = record.playback?.state === "LIVE";

  return (
    <article className="live-discovery-card">
      <div
        className={`live-card-visual${mediaReady ? " live-card-visual-ready" : ""}`}
        role="img"
        aria-label={mediaReady ? "直播视频已准备好" : "专家直播预告封面"}
      >
        <span className="live-visual-badge">{runtimeLabel}</span>
        <span className="live-cover-avatar" aria-hidden="true">{record.speaker.slice(0, 1)}</span>
        <strong>{record.speaker}</strong>
        <span className="live-cover-topic">聊聊「{record.problem_tags[0]}」</span>
        {mediaReady ? <span className="live-play-glyph" aria-hidden="true">▶</span> : null}
      </div>
      <div className="live-card-topline">
        <span className="live-pill">{runtimeLabel}</span>
        <span className="live-status-chip">内容已审核</span>
      </div>
      <h3>{record.title}</h3>
      <div className="live-expert-line">
        <span className="live-expert-avatar" aria-hidden="true">{record.speaker.slice(0, 1)}</span>
        <span className="live-card-speaker">{record.speaker}</span>
        <span className="live-expert-trust">适合{record.applicable_scope}</span>
      </div>
      <div className="live-problem-tags" aria-label="家庭问题标签">
        {record.problem_tags.map((tag) => <span key={tag}>#{tag}</span>)}
      </div>
      <p className="live-card-summary-copy">{record.expert_summary}</p>
      <p className="live-card-time"><span aria-hidden="true">◷</span> {record.starts_at} — {record.ends_at.slice(11)}</p>
      {onOpenDetail ? (
        <button className="live-detail-button" type="button" onClick={onOpenDetail}>
          {mediaReady ? "进入直播间" : "查看直播详情"}
        </button>
      ) : (
        <span className="live-locked-action">回看暂未开放</span>
      )}
    </article>
  );
}
