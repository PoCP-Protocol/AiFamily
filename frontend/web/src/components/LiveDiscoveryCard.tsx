import type { LiveRecord } from "../live/liveCatalog";

type Props = {
  record: LiveRecord;
  onOpenDetail: () => void;
};

export function LiveDiscoveryCard({ record, onOpenDetail }: Props) {
  return (
    <article className="live-discovery-card">
      <div className="live-card-topline">
        <span className="live-pill">专家直播</span>
        <span className="live-readonly">只读信息</span>
      </div>
      <h3>{record.title}</h3>
      <p className="live-card-speaker">主讲人 · {record.speaker}</p>
      <dl className="live-card-summary">
        <div>
          <dt>适用范围</dt>
          <dd>{record.applicable_scope}</dd>
        </div>
        <div>
          <dt>时间</dt>
          <dd>{record.starts_at} — {record.ends_at}</dd>
        </div>
      </dl>
      <button className="live-detail-button" type="button" onClick={onOpenDetail}>
        查看直播详情
      </button>
    </article>
  );
}
