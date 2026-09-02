import { useEffect, useMemo, useReducer, useState } from "react";
import {
  type ExperienceApiClient,
  ExperienceApiError,
  type ExperienceScope,
} from "./api/client";
import { createDefaultExperienceApiClient } from "./api/clientFactory";
import { DecisionActions } from "./components/DecisionActions";
import { DraftResult } from "./components/DraftResult";
import { ExpressionInput, type ExpressionForm } from "./components/ExpressionInput";
import { RunStatus } from "./components/RunStatus";
import { ReplayTimeline } from "./components/ReplayTimeline";
import { LiveExperience } from "./components/LiveExperience";
import { LiveModeratorConsole } from "./components/LiveModeratorConsole";
import { LiveRuntimeConsole } from "./components/LiveRuntimeConsole";
import { LiveSessionControlConsole } from "./components/LiveSessionControlConsole";
import { LiveSettlementConsole } from "./components/LiveSettlementConsole";
import { LiveServiceOfferingPage } from "./components/LiveServiceOfferingPage";
import { LiveAIAssistantConsole } from "./components/LiveAIAssistantConsole";
import { LiveIncidentConsole } from "./components/LiveIncidentConsole";
import {
  resolveLiveAIBaseUrl,
  resolveLiveIncidentBaseUrl,
  resolveLiveCommerceBaseUrl,
  resolveLiveControlBaseUrl,
  resolveLiveInteractionBaseUrl,
  resolveLiveObservabilityBaseUrl,
} from "./live/liveCatalog";
import { initialStudioState, studioReducer } from "./state/experienceStudio";

type Props = { client?: ExperienceApiClient };

const defaultScope: ExperienceScope = {
  tenant_id: "demo-tenant",
  region_id: "CN",
  family_id: "demo-family",
  subject_ids: ["guardian-demo"],
  purpose: "family_growth_experience",
  consent_version: "v1",
  consent_granted: false,
  locale: "zh-CN",
};

const newRunId = () =>
  typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `web-run-${Date.now()}`;

const defaultClient: ExperienceApiClient = createDefaultExperienceApiClient(import.meta.env);

export default function App({ client = defaultClient }: Props) {
  const [liveSurface, setLiveSurface] = useState<"viewer" | "ops" | "service">(
    window.location.hash === "#live-ops"
      ? "ops"
      : window.location.hash === "#live-service"
        ? "service"
        : "viewer",
  );
  const [state, dispatch] = useReducer(studioReducer, initialStudioState);
  const [runId, setRunId] = useState(newRunId);
  const [form, setForm] = useState<ExpressionForm>({
    payload: { expression: "" },
    media_inputs: [],
    scope: defaultScope,
  });
  const idempotencyKey = useMemo(() => `web:${runId}`, [runId]);

  const createDraft = async () => {
    dispatch({ type: "VALIDATING" });
    if (!form.payload.expression.trim()) {
      dispatch({
        type: "FAILED",
        error: new ExperienceApiError("INVALID_INPUT", "refused", "请先写下想被理解的家庭表达。"),
      });
      return;
    }
    if (!form.scope.consent_granted) {
      dispatch({
        type: "FAILED",
        error: new ExperienceApiError("CONSENT_REQUIRED", "refused", "提交前需要同意本次用途的数据读取。"),
      });
      return;
    }
    dispatch({ type: "RUNNING" });
    try {
      const draft = await client.createDraft(
        {
          run_id: runId,
          use_case: "family_expression_understanding",
          prompt_version: "experience-studio.v1",
          schema_version: "experience-draft.v1",
          data_class: "FAMILY_PRIVATE_TEXT",
          context_snapshot_ref: `web-context:${runId}`,
          payload: form.payload,
          input_refs: form.media_inputs.map((media) => media.uri),
          media_inputs: form.media_inputs,
          scope: form.scope,
        },
        idempotencyKey,
      );
      dispatch({ type: "DRAFT_READY", draft });
    } catch (error) {
      dispatch({
        type: "FAILED",
        error: error instanceof ExperienceApiError
          ? error
          : new ExperienceApiError("INVALID_INPUT", "refused", "暂时无法生成草案，请稍后再试。"),
      });
    }
  };

  const retry = async () => {
    dispatch({ type: "RETRYING" });
    await createDraft();
  };

  const decide = async (decision: "confirm" | "reject" | "rewrite") => {
    const receipt = await client.decide({ run_id: runId, decision }, `${idempotencyKey}:${decision}`);
    if (receipt.status === "pending_human_confirmation") {
      dispatch({ type: "HUMAN_REVIEW", message: "请求已提交，等待人工闸门确认；草案仍不是家庭事实。" });
    } else {
      dispatch({ type: "MESSAGE", message: "这份草案已暂不采用，家庭事实没有改变。" });
    }
  };

  const requestHuman = async () => {
    await client.requestHuman({ run_id: runId, reason: "家庭成员希望人工核对这份理解草案。" }, `${idempotencyKey}:human`);
    dispatch({ type: "HUMAN_REVIEW", message: "已请求人工顾问，等待人工确认。" });
  };

  const deleteRun = async () => {
    await client.deleteRun(runId, `${idempotencyKey}:delete`);
    dispatch({ type: "DELETED" });
  };

  const replayRun = async () => {
    try {
      const replay = await client.replayRun(runId);
      dispatch({ type: "REPLAY_READY", replay });
    } catch (error) {
      dispatch({
        type: "FAILED",
        error: error instanceof ExperienceApiError
          ? error
          : new ExperienceApiError("MEDIA_DELETED", "deleted", "这次体验已无法回放。"),
      });
    }
  };

  const submitFeedback = async (signal: "helpful" | "not_helpful") => {
    const benchmark = state.draft?.benchmark;
    await client.submitFeedback({
      run_id: runId,
      signal,
      draft_version: state.draft?.draft_version,
      model_version: benchmark?.model_version,
      candidate_id: benchmark?.candidate_id,
      benchmark_report_ref: benchmark?.benchmark_report_ref,
    }, `${idempotencyKey}:feedback:${signal}`);
    dispatch({ type: "MESSAGE", message: signal === "helpful" ? "已记录“有帮助”的反馈。" : "已记录反馈，后续可以改写这份草案。" });
  };

  const reset = () => {
    const nextRunId = newRunId();
    setRunId(nextRunId);
    setForm({ payload: { expression: "" }, media_inputs: [], scope: defaultScope });
    dispatch({ type: "RESET" });
  };

  const hasDraft = Boolean(state.draft);
  const canAct = hasDraft && state.status === "success";

  useEffect(() => {
    const updateSurface = () => setLiveSurface(
      window.location.hash === "#live-ops"
        ? "ops"
        : window.location.hash === "#live-service"
          ? "service"
          : "viewer",
    );
    window.addEventListener("hashchange", updateSurface);
    return () => window.removeEventListener("hashchange", updateSurface);
  }, []);

  return (
    <main className="app-shell">
      <header className="topbar live-topbar">
        <div className="brand-lockup">
          <div className="brand-mark live-brand" aria-label="小橘灯">小橘灯</div>
          <span className="brand-context">AiFamily · 专家直播</span>
        </div>
        <nav className="live-nav" aria-label="直播导航">
          <a href="#live-home">直播首页</a>
          {import.meta.env.DEV ? <a href="#live-ops">专家工作台</a> : null}
        </nav>
        <span className="environment-tag">SANDBOX · DEV_ONLY</span>
      </header>
      {liveSurface === "ops" ? (
        <div className="live-ops-dashboard">
          <div className="live-ops-dashboard-title">
            <div>
              <span>LIVE COMMAND CENTER</span>
              <h1>小橘灯直播指挥中心</h1>
            </div>
            <p>场次、审核、运行、结算与 AI 内容生产同屏协作。</p>
          </div>
          <LiveSessionControlConsole
            controlBaseUrl={resolveLiveControlBaseUrl(import.meta.env)}
          />
          <LiveModeratorConsole
            interactionBaseUrl={resolveLiveInteractionBaseUrl(import.meta.env)}
            controlBaseUrl={resolveLiveControlBaseUrl(import.meta.env)}
          />
          <LiveIncidentConsole incidentBaseUrl={resolveLiveIncidentBaseUrl(import.meta.env)} />
          <LiveSettlementConsole commerceBaseUrl={resolveLiveCommerceBaseUrl(import.meta.env)} />
          <LiveRuntimeConsole
            observabilityBaseUrl={resolveLiveObservabilityBaseUrl(import.meta.env)}
          />
          <LiveAIAssistantConsole aiBaseUrl={resolveLiveAIBaseUrl(import.meta.env)} />
        </div>
      ) : liveSurface === "service" ? (
        <LiveServiceOfferingPage commerceBaseUrl={resolveLiveCommerceBaseUrl(import.meta.env)} />
      ) : (
        <LiveExperience environment={import.meta.env} />
      )}
      <details className="secondary-experience">
        <summary>家庭理解工作台（次级入口）</summary>
        <div className="page-grid">
          <div className="intro-column">
            <p className="eyebrow">家庭成长 · AI 原生体验</p>
            <h1>先被理解，再一起决定。</h1>
            <p className="intro-copy">把一次真实表达变成一份可核对、可暂停、可请求人工的理解草案。AI 只提出建议，家庭保留决定权。</p>
            <RunStatus status={state.status} message={state.error?.message ?? state.message} />
            {state.error?.code === "TIMEOUT" ? <button className="secondary-button retry-button" type="button" onClick={retry}>使用同一请求重试</button> : null}
            {state.status === "deleted" ? <button className="secondary-button retry-button" type="button" onClick={reset}>开始新的体验</button> : null}
          </div>
          <div className="studio-column">
            <ExpressionInput value={form} disabled={state.status === "running" || state.status === "retrying"} onChange={setForm} onSubmit={createDraft} />
            <DraftResult draft={state.draft} onDelete={deleteRun} onReplay={() => void replayRun()} onHelpful={() => void submitFeedback("helpful")} onNotHelpful={() => void submitFeedback("not_helpful")} feedbackDisabled={state.status !== "success"} />
            <ReplayTimeline replay={state.replay} />
            <DecisionActions disabled={!canAct} onConfirm={() => void decide("confirm")} onRewrite={() => void decide("rewrite")} onReject={() => void decide("reject")} onHuman={() => void requestHuman()} />
          </div>
        </div>
      </details>
      <footer className="footer-note">DRAFT 输出带有 provenance；不会自动写入 Family、Journey、Service 或 Commerce 事实。</footer>
    </main>
  );
}
