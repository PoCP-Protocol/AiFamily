import type { RunStatus } from "../api/client";

const labels: Record<RunStatus, string> = {
  idle: "等你写下一件小事",
  validating: "正在准备",
  running: "正在整理你说的事",
  partial: "已经整理了一部分",
  success: "支持卡准备好了",
  refused: "这次暂时无法继续",
  timeout: "连接有点慢",
  retrying: "正在再试一次",
  human_review: "已收到，等人工帮你看",
  deleted: "这次内容已删除",
};

type Props = { status: RunStatus; message?: string | null };

export function RunStatus({ status, message }: Props) {
  return (
    <section className={`status status-${status}`} aria-live="polite" aria-atomic="true">
      <span className="status-dot" aria-hidden="true" />
      <div>
        <strong>{labels[status]}</strong>
        {message ? <p>{message}</p> : null}
      </div>
    </section>
  );
}

export { labels as runStatusLabels };
