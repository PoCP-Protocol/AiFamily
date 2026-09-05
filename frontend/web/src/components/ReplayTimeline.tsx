import type { ReplaySnapshot } from "../api/client";

type Props = { replay: ReplaySnapshot | null };

export function ReplayTimeline({ replay }: Props) {
  if (!replay) return null;
  return (
    <section className="panel replay-panel" aria-labelledby="replay-heading">
      <div className="section-kicker">事件回放</div>
      <h2 id="replay-heading">这次体验发生了什么</h2>
      <ol className="replay-list">
        {replay.entries.map((entry) => (
          <li key={`${entry.at}-${entry.label}`}>
            <span className="replay-node">{entry.at}</span>
            <span>{entry.label}</span>
          </li>
        ))}
      </ol>
      <p className="muted">回放只读取 Experience Gateway 的事件投影，不重放模型调用，也不改变家庭事实。</p>
    </section>
  );
}
