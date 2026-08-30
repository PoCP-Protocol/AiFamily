import type { RunStatus } from "../api/client";

const labels: Record<RunStatus, string> = {
  idle: "等待输入",
  validating: "正在检查同意与输入",
  running: "AI 正在理解",
  partial: "已生成部分结果",
  success: "理解草案已生成",
  refused: "请求被安全拒绝",
  timeout: "模型响应超时",
  retrying: "正在安全重试",
  human_review: "等待人工确认",
  deleted: "内容已删除",
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
