import { useState } from "react";
import {
  HttpOperatorReviewApiClient,
  OperatorReviewApiError,
  type OperatorReviewApiClient,
  type ProductDefinitionReviewDecision,
  type ProductDefinitionReviewTask,
  type ReviewOutcome,
} from "./operatorReviewApi";

type Props = { client?: OperatorReviewApiClient };

const OUTCOME_LABELS: Record<ReviewOutcome, string> = {
  ACCEPT: "接受并进入 PDM 草案",
  REJECT: "拒绝本次提案",
  ESCALATE: "升级给更高权限复核",
};

function newIdempotencyKey(taskId: string): string {
  const suffix = typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}`;
  return `product-definition-review:${taskId}:${suffix}`;
}

export function ProductDefinitionOperatorReviewWorkbench({
  client = new HttpOperatorReviewApiClient(),
}: Props) {
  const [tasks, setTasks] = useState<ProductDefinitionReviewTask[]>([]);
  const [selected, setSelected] = useState<ProductDefinitionReviewTask | null>(null);
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState<{ outcome: ReviewOutcome; key: string } | null>(null);
  const [decision, setDecision] = useState<ProductDefinitionReviewDecision | null>(null);
  const [error, setError] = useState<OperatorReviewApiError | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    setTasks([]);
    setSelected(null);
    setDecision(null);
    setPending(null);
    try {
      setTasks(await client.listOpenTasks());
    } catch (cause) {
      setError(cause instanceof OperatorReviewApiError
        ? cause
        : new OperatorReviewApiError("INVALID_RESPONSE", "评审队列读取失败。"));
    } finally {
      setLoading(false);
    }
  };

  const open = async (expected: ProductDefinitionReviewTask) => {
    setLoading(true);
    setError(null);
    setDecision(null);
    setPending(null);
    setReason("");
    try {
      setSelected(await client.getTask(expected.task_id, expected));
    } catch (cause) {
      setError(cause instanceof OperatorReviewApiError
        ? cause
        : new OperatorReviewApiError("INVALID_RESPONSE", "评审任务读取失败。"));
    } finally {
      setLoading(false);
    }
  };

  const prepare = (outcome: ReviewOutcome) => {
    if (!selected || !reason.trim() || selected.status !== "OPEN") return;
    setPending({ outcome, key: newIdempotencyKey(selected.task_id) });
    setDecision(null);
  };

  const confirm = async () => {
    if (!selected || !pending || !reason.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const result = await client.decide(selected, pending.outcome, reason, pending.key);
      setDecision(result);
      setSelected(result.task);
      setTasks((current) => current.filter(({ task_id }) => task_id !== result.task.task_id));
      setPending(null);
    } catch (cause) {
      setError(cause instanceof OperatorReviewApiError
        ? cause
        : new OperatorReviewApiError("INVALID_RESPONSE", "人工决定提交失败。"));
    } finally {
      setLoading(false);
    }
  };

  const expired = selected ? Date.parse(selected.expires_at) <= Date.now() : false;
  const canDecide = selected?.status === "OPEN" && !expired && reason.trim().length > 0 && !loading;
  const args = selected?.action_arguments;

  return (
    <section aria-busy={loading} aria-label="PDM Operator Review" className="panel product-definition-review-workbench">
      <div className="section-kicker">IPD Gate · Human Named Action · PDM</div>
      <h2>PDM 人工评审队列</h2>
      <p className="muted">只审阅服务端 OPEN 提案。AI 不会自动通过，浏览器也不能提交身份、租户、三区或 provenance。</p>
      <button className="secondary-button" disabled={loading} onClick={() => void refresh()} type="button">
        {loading ? "读取中…" : "刷新待评审任务"}
      </button>

      {error ? <p role="alert">错误：{error.code} · {error.message}</p> : null}
      {!loading && tasks.length === 0 ? <p role="status">当前没有已加载的 OPEN 评审任务。</p> : null}

      {tasks.length > 0 ? (
        <ol aria-label="待评审任务" className="review-task-list">
          {tasks.map((task) => (
            <li key={task.task_id}>
              <button className="text-button" onClick={() => void open(task)} type="button">
                {task.task_id} · {String(task.action_arguments.product_kind ?? "未提供")}
              </button>
              <small>{task.risk_level} · 截止 {new Date(task.expires_at).toLocaleString()}</small>
            </li>
          ))}
        </ol>
      ) : null}

      {selected ? (
        <article aria-label="评审任务详情" className="review-task-detail">
          <h3>只读提案快照</h3>
          <dl className="provenance-grid">
            <div><dt>Task</dt><dd>{selected.task_id}</dd></div>
            <div><dt>Proposal</dt><dd>{selected.proposal_id}</dd></div>
            <div><dt>Draft</dt><dd>{selected.draft_id}</dd></div>
            <div><dt>Provenance</dt><dd>{selected.provenance_ref}</dd></div>
            <div><dt>Concept</dt><dd>{String(args?.concept_id)}</dd></div>
            <div><dt>三区评估</dt><dd>{String(args?.zone_assessment_id)}</dd></div>
            <div><dt>产品形态</dt><dd>{String(args?.product_kind)} · {String(args?.duration_days)} 天</dd></div>
            <div><dt>风险 / 状态</dt><dd>{selected.risk_level} · {selected.status}</dd></div>
          </dl>
          <p><strong>主矛盾：</strong>{String(args?.primary_contradiction ?? "未提供")}</p>
          <p><strong>市场证据：</strong>{Array.isArray(args?.market_insight_refs) ? args.market_insight_refs.join(", ") : "未提供"}</p>
          <p><strong>组件：</strong>{Array.isArray(args?.component_ids) ? args.component_ids.join(", ") : "未提供"}</p>
          {expired ? <p role="status">任务已超过评审截止时间，不能提交决定。</p> : null}

          <label>
            人工决策理由
            <textarea
              rows={3}
              value={reason}
              onChange={(event) => {
                setReason(event.target.value);
                setPending(null);
              }}
              placeholder="说明证据判断、风险与下一步"
            />
          </label>
          <div className="result-actions">
            {(Object.keys(OUTCOME_LABELS) as ReviewOutcome[]).map((outcome) => (
              <button
                className={outcome === "ACCEPT" ? "human-button" : "secondary-button"}
                disabled={!canDecide}
                key={outcome}
                onClick={() => prepare(outcome)}
                type="button"
              >
                准备：{OUTCOME_LABELS[outcome]}
              </button>
            ))}
          </div>
        </article>
      ) : null}

      {pending && selected ? (
        <section aria-label="确认 PDM 人工决定" className="callout">
          <strong>二次确认 · {pending.outcome}</strong>
          <p>{OUTCOME_LABELS[pending.outcome]}：{selected.proposal_id}</p>
          <p>确认后由服务端记录决定；只有 ACCEPT 才生成待工作器执行的 NamedActionRequest。</p>
          <button className="human-button" disabled={loading} onClick={() => void confirm()} type="button">
            确认提交人工决定
          </button>
        </section>
      ) : null}

      {decision ? (
        <output aria-label="PDM 人工决定结果" className="callout">
          <strong>DECIDED · {decision.task.decision_outcome}</strong>
          <p>决策：{decision.task.decision_id} · 操作人：{decision.actor_id}</p>
          <p>{decision.task.decision_reason}</p>
          <p role="status">
            {decision.execution_status === "PENDING"
              ? `Named Action ${decision.task.request_id} 已生成，等待工作器执行；尚不代表 ProductDefinition 已创建。`
              : "本决定不生成 Named Action。"}
          </p>
        </output>
      ) : null}
    </section>
  );
}
