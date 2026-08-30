import type { LiveRecord } from "../live/liveCatalog";

type Props = {
  record: LiveRecord;
  onBack: () => void;
};

export function LiveDetailPage({ record, onBack }: Props) {
  return (
    <article className="live-detail-page" aria-labelledby="live-detail-heading">
      <div className="live-detail-header">
        <div>
          <p className="live-kicker">H-LIVE-01 · 只读详情</p>
          <h3 id="live-detail-heading">{record.title}</h3>
        </div>
        <span className="live-status-badge">{record.status}</span>
      </div>
      <section className="live-video-container" aria-labelledby="live-video-heading" data-playback-state={record.playback_state}>
        <div className="live-video-frame" role="status">
          <span className="live-readonly">PLAYER CONTAINER · FAIL-CLOSED</span>
          <h4 id="live-video-heading">视频暂不可用</h4>
          <p>等待授权后才可评估播放能力；当前不会加载媒体。</p>
          <span className="live-video-state">{record.playback_state}</span>
        </div>
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
