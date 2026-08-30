import type { ReplaySnapshot } from "../api/client";

type Props = { replay: ReplaySnapshot | null };

export function ReplayTimeline({ replay }: Props) {
  if (!replay) return null;
  return (
    <section className="panel replay-panel" aria-labelledby="replay-heading">
      <div className="section-kicker">这次体验的记录</div>
      <h2 id="replay-heading">你刚才做过什么</h2>
      <ol className="replay-list">
        {replay.entries.map((entry) => (
          <li key={`${entry.at}-${entry.label}`}>
            <span className="replay-node">{entry.at}</span>
            <span>{humanizeReplayEntry(entry.label)}</span>
          </li>
        ))}
      </ol>
      <p className="muted">这份记录只帮助你回看过程，不会重新执行任何动作。</p>
    </section>
  );
}

function humanizeReplayEntry(label: string): string {
  if (label.includes("表达已接收")) return "你提交了一段表达";
  if (label.includes("草案生成")) return "支持卡已经准备好";
  if (label.includes("等待家庭确认")) return "等你决定要不要继续";
  return "你完成了一步操作";
}
