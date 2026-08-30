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
      <dl className="live-detail-grid">
        <div><dt>主讲人</dt><dd>{record.speaker}</dd></div>
        <div><dt>适用范围</dt><dd>{record.applicable_scope}</dd></div>
        <div><dt>开始时间</dt><dd>{record.starts_at}</dd></div>
        <div><dt>结束时间</dt><dd>{record.ends_at}</dd></div>
        <div><dt>审核引用</dt><dd>{record.review_ref}</dd></div>
        <div><dt>版本</dt><dd>{record.version}</dd></div>
        <div><dt>family visibility</dt><dd>{record.family_visibility}</dd></div>
        <div><dt>as_of</dt><dd>{record.as_of}</dd></div>
        <div><dt>source</dt><dd>{record.source}</dd></div>
        <div><dt>fixture</dt><dd>{record.fixture ? "true · DEV only" : "false"}</dd></div>
      </dl>
      <p className="live-detail-note">本页仅展示审核过的只读字段，不提供互动或状态变更。</p>
      <button className="live-back-button" type="button" onClick={onBack}>
        返回直播发现
      </button>
    </article>
  );
}
