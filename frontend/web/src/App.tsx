import { useMemo, useReducer, useState } from "react";
import {
  type ExperienceApiClient,
  ExperienceApiError,
  type ExperienceScope,
} from "./api/client";
import { createDefaultExperienceApiClient } from "./api/clientFactory";
import { DecisionActions } from "./components/DecisionActions";
import { DraftResult } from "./components/DraftResult";
import { ExpressionInput, type ExpressionForm } from "./components/ExpressionInput";
import { LiveExperience } from "./components/LiveExperience";
import { ReplayTimeline } from "./components/ReplayTimeline";
import { RunStatus } from "./components/RunStatus";
import { initialStudioState, studioReducer } from "./state/experienceStudio";

type Props = { client?: ExperienceApiClient };
type View = "home" | "expression" | "assessment" | "result" | "action" | "live";

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

function friendlyError(error: ExperienceApiError): ExperienceApiError {
  const copy: Record<ExperienceApiError["code"], string> = {
    CONSENT_REQUIRED: "请先确认这次内容只用于整理你的表达。",
    PROVIDER_NOT_ADMITTED: "现在还没准备好为这段内容提供支持，请稍后再试。",
    TIMEOUT: "连接有点慢，可以再试一次。",
    MEDIA_DELETED: "这次内容已经删除，我们不会继续使用它。",
    RUN_NOT_FOUND: "没有找到这次体验，可以重新开始。",
    CONFLICT: "刚才的内容有变化，请重新试一次。",
    SCOPE_MISMATCH: "这次内容暂时无法在当前家庭中继续。",
    INVALID_INPUT: "请再写下一件具体发生的小事。",
  };
  return new ExperienceApiError(error.code, error.status, copy[error.code]);
}

function blankForm(): ExpressionForm {
  return { payload: { expression: "" }, media_inputs: [], scope: defaultScope };
}

export default function App({ client = defaultClient }: Props) {
  const [state, dispatch] = useReducer(studioReducer, initialStudioState);
  const [view, setView] = useState<View>("home");
  const [mode, setMode] = useState<"expression" | "assessment">("expression");
  const [runId, setRunId] = useState(newRunId);
  const [form, setForm] = useState<ExpressionForm>(blankForm);
  const [actionChecked, setActionChecked] = useState(false);
  const idempotencyKey = useMemo(() => `web:${runId}`, [runId]);

  const startFlow = (nextMode: "expression" | "assessment") => {
    setMode(nextMode);
    setRunId(newRunId());
    setForm(blankForm());
    setActionChecked(false);
    dispatch({ type: "RESET" });
    setView(nextMode);
  };

  const createDraft = async () => {
    dispatch({ type: "VALIDATING" });
    if (!form.payload.expression.trim()) {
      dispatch({ type: "FAILED", error: new ExperienceApiError("INVALID_INPUT", "refused", "请再写下一件具体发生的小事。") });
      return;
    }
    if (!form.scope.consent_granted) {
      dispatch({ type: "FAILED", error: new ExperienceApiError("CONSENT_REQUIRED", "refused", "请先确认这次内容只用于整理你的表达。") });
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
      setView("result");
    } catch (error) {
      const apiError = error instanceof ExperienceApiError
        ? error
        : new ExperienceApiError("INVALID_INPUT", "refused", "现在还没准备好，请稍后再试。");
      dispatch({ type: "FAILED", error: friendlyError(apiError) });
    }
  };

  const retry = async () => {
    dispatch({ type: "RETRYING" });
    await createDraft();
  };

  const decide = async (decision: "confirm" | "reject" | "rewrite") => {
    const receipt = await client.decide({ run_id: runId, decision }, `${idempotencyKey}:${decision}`);
    if (receipt.status === "pending_human_confirmation") {
      dispatch({ type: "HUMAN_REVIEW", message: "已收到，我们会先由人工帮你核对；家庭内容不会自动改变。" });
    } else {
      dispatch({ type: "MESSAGE", message: "这次理解先放下，家庭内容没有改变。" });
    }
  };

  const requestHuman = async () => {
    await client.requestHuman({ run_id: runId, reason: "家庭成员希望人工核对这份理解。" }, `${idempotencyKey}:human`);
    dispatch({ type: "HUMAN_REVIEW", message: "已收到，我们会先由人工帮你核对。" });
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
      const apiError = error instanceof ExperienceApiError
        ? error
        : new ExperienceApiError("MEDIA_DELETED", "deleted", "这次体验已无法打开。");
      dispatch({ type: "FAILED", error: friendlyError(apiError) });
    }
  };

  const submitFeedback = async (signal: "helpful" | "not_helpful") => {
    await client.submitFeedback({ run_id: runId, signal, draft_version: state.draft?.draft_version }, `${idempotencyKey}:feedback:${signal}`);
    dispatch({ type: "MESSAGE", message: signal === "helpful" ? "谢谢，你的反馈已记下。" : "谢谢，我们会把这份理解改得更贴近你。" });
  };

  const backHome = () => setView("home");
  const hasDraft = Boolean(state.draft);
  const canAct = hasDraft && state.status === "success";

  return (
    <main className="app-shell">
      <header className="topbar journey-topbar">
        <button className="brand-button" type="button" onClick={backHome} aria-label="回到 AiFamily 首页">
          <span className="brand-mark">AiFamily</span>
          <span className="brand-context">家是港湾</span>
        </button>
        <nav className="journey-nav" aria-label="主导航">
          <button type="button" onClick={backHome}>首页</button>
          <button type="button" onClick={() => setView("live")}>专家内容</button>
        </nav>
      </header>

      {view === "home" ? (
        <section className="experience-home" aria-labelledby="home-heading">
          <div className="home-hero">
            <p className="eyebrow">给家庭留一点从容</p>
            <h1 id="home-heading">今天，想先让哪件小事轻一点？</h1>
            <p className="home-lede">不用准备完整答案，从一个刚刚发生的片段开始，我们一起找到今晚能试的一小步。</p>
          </div>
          <div className="home-actions" aria-label="开始一段家庭支持">
            <button className="home-card home-card-primary" type="button" onClick={() => startFlow("expression")}>
              <span className="home-card-icon" aria-hidden="true">说</span>
              <span className="home-card-copy"><strong>我想说一件家庭小事</strong><small>写下发生了什么，得到一张温和的支持卡</small></span>
              <span className="home-card-arrow" aria-hidden="true">→</span>
            </button>
            <button className="home-card" type="button" onClick={() => startFlow("assessment")}>
              <span className="home-card-icon" aria-hidden="true">看</span>
              <span className="home-card-copy"><strong>我想做一次小测评</strong><small>从一个困扰开始，看见可以先关注的地方</small></span>
              <span className="home-card-arrow" aria-hidden="true">→</span>
            </button>
            <button className="home-card" type="button" onClick={() => setView("live")}>
              <span className="home-card-icon" aria-hidden="true">听</span>
              <span className="home-card-copy"><strong>我想看专家内容 / 直播</strong><small>发现适合家庭的只读内容和专家场次</small></span>
              <span className="home-card-arrow" aria-hidden="true">→</span>
            </button>
          </div>
          <div className="home-note"><span aria-hidden="true">✦</span> 你可以随时停下，也可以回到刚才的地方。</div>
        </section>
      ) : null}

      {view === "live" ? (
        <>
          <button className="back-link page-back-link" type="button" onClick={backHome}>← 回到首页</button>
          <LiveExperience environment={import.meta.env} />
        </>
      ) : null}

      {view === "expression" || view === "assessment" ? (
        <section className="journey-page" aria-labelledby="journey-heading">
          <button className="back-link" type="button" onClick={backHome}>← 先回首页</button>
          <div className="journey-layout">
            <div className="journey-intro">
              <p className="eyebrow">{mode === "assessment" ? "从小测评开始" : "从一件小事开始"}</p>
              <h1 id="journey-heading">不用说得很完整。</h1>
              <p className="intro-copy">把此刻最在意的地方写下来就好。我们先听，再和你一起核对，不替你下结论。</p>
              <RunStatus status={state.status} message={state.error?.message ?? state.message} />
              {state.status === "timeout" ? <button className="secondary-button retry-button" type="button" onClick={retry}>再试一次</button> : null}
              {state.status === "deleted" ? <button className="secondary-button retry-button" type="button" onClick={() => startFlow("expression")}>重新开始</button> : null}
            </div>
            <div className="journey-form-column">
              <ExpressionInput value={form} mode={mode} disabled={state.status === "running" || state.status === "retrying"} onChange={setForm} onSubmit={createDraft} onCancel={backHome} />
            </div>
          </div>
        </section>
      ) : null}

      {view === "result" ? (
        <section className="journey-page" aria-labelledby="result-page-heading">
          <button className="back-link" type="button" onClick={() => setView("expression")}>← 回到刚才的表达</button>
          <div className="journey-result-layout">
            <div className="journey-intro">
              <p className="eyebrow">今天的家庭支持</p>
              <h1 id="result-page-heading">先看见，再决定。</h1>
              <p className="intro-copy">这张卡是一次可以被你校正的理解，不是给家庭贴上的标签。</p>
              <RunStatus status={state.status} message={state.error?.message ?? state.message} />
              {state.status === "deleted" ? <button className="secondary-button retry-button" type="button" onClick={() => startFlow("expression")}>重新开始</button> : null}
            </div>
            <div className="journey-form-column">
              <DraftResult
                draft={state.draft}
                expression={form.payload.expression}
                onChooseStep={() => { setActionChecked(false); setView("action"); }}
                onCorrect={() => setView("expression")}
                onDelete={() => void deleteRun()}
                onReplay={() => void replayRun()}
                onHelpful={() => void submitFeedback("helpful")}
                onNotHelpful={() => void submitFeedback("not_helpful")}
                feedbackDisabled={state.status !== "success"}
              />
              <ReplayTimeline replay={state.replay} />
              <DecisionActions disabled={!canAct} onConfirm={() => void decide("confirm")} onRewrite={() => void decide("rewrite")} onReject={() => void decide("reject")} onHuman={() => void requestHuman()} />
            </div>
          </div>
        </section>
      ) : null}

      {view === "action" && state.draft ? (
        <section className="journey-page action-page" aria-labelledby="action-heading">
          <button className="back-link" type="button" onClick={() => setView("result")}>← 回到支持卡</button>
          <div className="action-card panel">
            <div className="journey-stepper" aria-label="家庭支持步骤">
              <span>1 说一件小事</span><span>2 看见重点</span><span className="journey-step-active">3 试一小步</span>
            </div>
            <p className="eyebrow">今晚的家庭小步骤</p>
            <h1 id="action-heading">不用一次解决全部。</h1>
            <p className="action-lede">给自己一个很小、很具体的尝试，做完也可以告诉我们感觉如何。</p>
            <div className="action-suggestion"><span aria-hidden="true">☼</span><p>{state.draft.output.next_step}</p></div>
            <label className="action-check-row">
              <input type="checkbox" checked={actionChecked} onChange={(event) => setActionChecked(event.target.checked)} />
              <span>{actionChecked ? "我已经记下今晚想试的这一步" : "我今晚想先试这一步"}</span>
            </label>
            {actionChecked ? <p className="action-confirmation" role="status">已记下。明天可以从这里继续，不需要重新解释一遍。</p> : null}
            <div className="form-actions">
              <button className="secondary-button" type="button" onClick={() => setView("result")}>回到支持卡</button>
              <button className="primary-button" type="button" onClick={backHome}>回到首页</button>
            </div>
          </div>
        </section>
      ) : null}

      <footer className="footer-note">你拥有决定权：可以校正、暂停或删除这次体验。</footer>
    </main>
  );
}
