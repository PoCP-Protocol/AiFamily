import { useEffect, useMemo, useState } from "react";
import { HttpExperienceApiClient } from "../api/httpClient";
import type { ExperienceApiClient } from "../api/client";
import {
  FamilyGrowthApiClient,
  FamilyGrowthApiError,
  type AssessmentItem,
  type AssessmentProjection,
  type GrowthHypothesisProjection,
  type GrowthPathNode,
} from "./client";
import { createDevAccountSession } from "./client";

type Props = {
  familyId?: string;
  growthClient?: FamilyGrowthApiClient;
  experienceClient?: ExperienceApiClient;
};

type View = "loading" | "assessment" | "hypothesis" | "draft" | "path" | "error";

const newId = (prefix: string) =>
  `${prefix}-${typeof crypto.randomUUID === "function" ? crypto.randomUUID() : Date.now()}`;

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || undefined;
const apiToken = import.meta.env.VITE_API_TOKEN as string | undefined;

export function FamilyGrowthExperience({
  familyId = import.meta.env.VITE_FAMILY_ID || "family-a",
  growthClient,
  experienceClient,
}: Props) {
  const [sessionToken, setSessionToken] = useState(apiToken);
  const [authReady, setAuthReady] = useState(Boolean(apiToken || (growthClient && experienceClient)));
  const [authError, setAuthError] = useState<string | null>(null);
  const resolvedGrowthClient = useMemo(
    () => growthClient ?? new FamilyGrowthApiClient({ baseUrl: apiBaseUrl, accessToken: sessionToken }),
    [growthClient, sessionToken],
  );
  const resolvedExperienceClient = useMemo(
    () => experienceClient ?? new HttpExperienceApiClient({ baseUrl: apiBaseUrl, accessToken: sessionToken }),
    [experienceClient, sessionToken],
  );
  const [view, setView] = useState<View>("loading");
  const [assessment, setAssessment] = useState<AssessmentProjection | null>(null);
  const [hypothesis, setHypothesis] = useState<GrowthHypothesisProjection | null>(null);
  const [responses, setResponses] = useState<Record<string, string | boolean>>({});
  const [familyNote, setFamilyNote] = useState("");
  const [questionIndex, setQuestionIndex] = useState(0);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [draft, setDraft] = useState<{
    understanding: string;
    nextStep: string;
    limitations: string[];
    providerId?: string;
    model?: string;
    modelVersion?: string;
  } | null>(null);
  const [draftEditMode, setDraftEditMode] = useState(false);
  const [draftEditText, setDraftEditText] = useState("");
  const [growthPath, setGrowthPath] = useState<{
    next_step: string | null;
    path: Array<string | GrowthPathNode>;
    status: "DRAFT" | "REVIEW_REQUIRED" | "REJECTED" | "DEFERRED" | "EMPTY";
    feedback_signals?: string[];
  } | null>(null);
  const [message, setMessage] = useState("");

  const subject = assessment?.subjects?.[0];
  const items: AssessmentItem[] = assessment?.tool?.items ?? [];
  const answeredCount = useMemo(() => Object.keys(responses).length, [responses]);

  useEffect(() => {
    if (growthClient && experienceClient) {
      setAuthReady(true);
      return;
    }
    if (apiToken || !import.meta.env.DEV) {
      setAuthReady(true);
      return;
    }
    let active = true;
    void createDevAccountSession(
      import.meta.env.VITE_DEV_EXTERNAL_REF || `dev-parent:${familyId}`,
      { baseUrl: apiBaseUrl },
    )
      .then((session) => {
        if (!active) return;
        setSessionToken(session.token);
        setAuthReady(true);
      })
      .catch(() => {
        if (!active) return;
        setAuthError("暂时无法打开家庭空间，请稍后再试。");
      });
    return () => {
      active = false;
    };
  }, [familyId, growthClient, experienceClient]);

  useEffect(() => {
    if (authReady) void refreshAssessment();
  }, [authReady]);

  async function refreshAssessment() {
    setView("loading");
    try {
      const result = await resolvedGrowthClient.getAssessment(familyId);
      setAssessment(result);
      setView("assessment");
      setMessage("");
    } catch (error) {
      fail(error, "暂时无法打开家庭测评，请确认服务已启动。");
    }
  }

  async function startAssessment() {
    if (!subject || !assessment?.tool?.tool_ref) return;
    try {
      const result = await resolvedGrowthClient.startAssessment(
        familyId,
        { subject_person_id: subject.person_id, tool_ref: assessment.tool.tool_ref },
        newId("assessment-start"),
      );
      setSessionId(result.session_id ?? result.session?.assessment_session_id ?? null);
      setResponses({});
      setQuestionIndex(0);
      setMessage("我们先从几个维度理解这个家庭，没有分数，也没有排名。");
    } catch (error) {
      fail(error, "测评暂时无法开始。");
    }
  }

  async function submitAssessment() {
    if (!sessionId) return;
    try {
      for (const item of items) {
        if (responses[item.item_ref] === undefined) continue;
        await resolvedGrowthClient.saveAssessmentResponse(
          familyId,
          sessionId,
          { item_ref: item.item_ref, response_type: item.response_type, response_value: responses[item.item_ref] },
          newId(`assessment-response-${item.item_ref}`),
        );
      }
      await resolvedGrowthClient.submitAssessment(familyId, sessionId, newId("assessment-submit"));
      const next = await resolvedGrowthClient.getGrowthHypothesis(familyId);
      setHypothesis(next);
      setView("hypothesis");
      setMessage("我们把刚才说的内容整理好了，请先看看是否贴近你们的真实情况。");
    } catch (error) {
      fail(error, "测评结果暂时无法生成。");
    }
  }

  async function confirmUnderstanding() {
    const value = hypothesis?.hypothesis;
    const needId = value?.need_refs?.[0];
    const pathId = value?.action_candidate_refs?.[0];
    if (!value || !sessionId || !needId || !pathId) {
      fail(null, "当前理解还缺少可关联的家庭需要或成长路径，暂不生成虚假的下一步。");
      return;
    }
    try {
      await resolvedGrowthClient.decideGrowthHypothesis(
        familyId,
        { assessment_session_id: sessionId, hypothesis_ref: value.hypothesis_ref, decision_type: "CONFIRM" },
        newId("hypothesis-confirm"),
      );
      const nextRunId = newId("family-understanding");
      setRunId(nextRunId);
      const result = await resolvedExperienceClient.createDraft(
        {
          run_id: nextRunId,
          use_case: "family_assistant_conversation",
          prompt_version: "family-companion.v1",
          schema_version: "family-experience-draft.v1",
          data_class: "SYNTHETIC",
          context_snapshot_ref: "server-owned",
          payload: {
            expression: [
              value.statement ?? value.understanding ?? value.title ?? "请理解这个家庭当前的成长需要。",
              familyNote.trim() ? `家长补充：${familyNote.trim()}` : "",
            ].filter(Boolean).join("\n"),
            family_need_id: needId,
            path_id: pathId,
            path: [pathId],
          },
          input_refs: value.evidence_refs ?? [],
          media_inputs: [],
          scope: {
            tenant_id: "synthetic-dev",
            region_id: "CN",
            family_id: familyId,
            subject_ids: subject ? [subject.person_id] : [],
            purpose: "family_assistant_conversation",
            consent_version: "synthetic-consent.v1",
            consent_granted: true,
            locale: "zh-CN",
          },
        },
        newId("experience-draft"),
      );
      if (!result.output.understanding?.trim() || !result.output.next_step?.trim()) {
        fail(null, "当前没有足够内容形成可核对的家庭理解，暂不生成下一步。");
        return;
      }
      setDraft({
        understanding: result.output.understanding,
        nextStep: result.output.next_step,
        limitations: result.limitations,
        providerId: result.provenance.provider_id,
        model: result.provenance.model,
        modelVersion: result.provenance.model_version,
      });
      setDraftEditText(result.output.understanding);
      setDraftEditMode(false);
      setView("draft");
      setMessage("这是一段可以一起修改的理解。你们认可之前，它不会成为家庭结论。");
    } catch (error) {
      fail(error, "这次暂时没能整理好，请稍后再试。");
    }
  }

  async function acceptDraft() {
    if (!runId) return;
    try {
      await resolvedExperienceClient.decide({ run_id: runId, decision: "confirm" }, newId("draft-confirm"));
      const result = await resolvedGrowthClient.getGrowthPath(familyId, runId);
      setGrowthPath(result);
      setView("path");
      setMessage(
        result.status === "DRAFT"
          ? "成长方向已经准备好，请把它当作共同讨论的起点。"
          : "这次暂时没有可确认的成长方向。",
      );
    } catch (error) {
      fail(error, "成长方向暂时无法读取。");
    }
  }

  async function rewriteDraft() {
    if (!runId || !draftEditText.trim()) return;
    try {
      await resolvedExperienceClient.decide(
        { run_id: runId, decision: "rewrite", replacement_text: draftEditText.trim(), reason: "家长修订 AI 理解" },
        newId("draft-rewrite"),
      );
      setDraft((current) => current ? { ...current, understanding: draftEditText.trim() } : current);
      setDraftEditMode(false);
      setMessage("已记录你的修订。接下来看到的成长方向会以这份理解为起点。");
    } catch (error) {
      fail(error, "修订暂时无法保存。");
    }
  }

  function fail(error: unknown, fallback: string) {
    setView("error");
    setMessage(error instanceof FamilyGrowthApiError ? `${fallback}（${error.status}）` : fallback);
  }

  if (authError) return <main className="family-growth-shell"><p className="family-growth-error">{authError}</p><button className="primary-button" onClick={() => window.location.reload()}>重新连接</button></main>;
  if (!authReady || view === "loading") return <main className="family-growth-shell"><p>正在打开家庭成长空间…</p></main>;
  if (view === "error") {
    return <main className="family-growth-shell"><p className="family-growth-error">{message}</p><button className="primary-button" onClick={() => void refreshAssessment()}>重新打开</button></main>;
  }

  return (
    <main className="family-growth-shell">
      <header className="family-growth-header"><span className="family-growth-brand">AiFamily</span><span className="family-growth-private"><i /> 只属于这个家</span></header>
      <section className="family-growth-workspace">
        <div className="family-growth-workspace-heading">
          <div>
            <p className="family-growth-kicker">家庭成长工作台</p>
            <h1>今天，先处理<br /><em>一件事。</em></h1>
          </div>
          <p className="family-growth-workspace-note">把事实、分歧和想要的变化放在一起。系统只提供整理和视角，决定权在家人。</p>
        </div>
        {!sessionId && <div className="family-growth-entry">
          <div className="family-growth-entry-top"><span>新的家庭记录</span><span>约 3 分钟</span></div>
          <label><span>你想先处理哪一件事？</span><textarea aria-label="首页记录家庭问题" value={familyNote} onChange={(event) => setFamilyNote(event.target.value)} placeholder="例如：每天写作业前都会争吵，我想先弄清楚冲突是怎么开始的。" /></label>
          <div className="family-growth-entry-bottom"><span>仅对这个家庭可见 · 可以随时暂停</span><button className="family-growth-hero-cta" disabled={!subject || !assessment?.tool} onClick={() => void startAssessment()}><b>开始整理</b><strong>→</strong></button></div>
        </div>}
      </section>
      <section className="family-growth-progress" aria-label="家庭成长流程">
        {[["01", "记录问题"], ["02", "核对理解"], ["03", "决定下一步"]].map(([number, label], index) => (
          <div className={index <= (view === "assessment" ? 0 : view === "hypothesis" ? 1 : 2) ? "active" : ""} key={number}><b>{number}</b><span>{label}</span></div>
        ))}
      </section>
      {view === "assessment" && sessionId && (
        <section className="family-growth-panel">
          <div className="family-growth-panel-heading"><div><span className="family-growth-step">记录问题</span><h2>你想先处理哪一件家庭问题？</h2><p className="family-growth-panel-intro">选择一个具体场景。后面的建议会以你提供的事实为依据。</p></div><span className="family-growth-count">{answeredCount}/{items.length}<small> 已回答</small></span></div>
          {subject ? <p className="family-growth-subject">当前记录对象：{subject.display_name}。你也可以补充其他家庭成员的感受。</p> : <p className="family-growth-error">当前还没有可以开始的家庭成员。</p>}
          <label className="family-growth-note"><span>补充事实、分歧或你希望改变的结果（可选）</span><textarea aria-label="补充说说最近发生了什么" value={familyNote} onChange={(event) => setFamilyNote(event.target.value)} placeholder="例如：工作日晚上八点开始写作业。家长持续催促，孩子拒绝沟通，最后双方都退出了讨论。" /></label>
          {!sessionId ? <button className="primary-button family-growth-cta" disabled={!subject || !assessment?.tool} onClick={() => void startAssessment()}>开始了解这个家 <span>→</span></button> : <div className="family-growth-items">
            {items[questionIndex] && <AssessmentItemView item={items[questionIndex]} value={responses[items[questionIndex].item_ref]} onChange={(value) => setResponses((current) => ({ ...current, [items[questionIndex].item_ref]: value }))} />}
            <div className="family-growth-question-nav"><button className="secondary-button" disabled={questionIndex === 0} onClick={() => setQuestionIndex((index) => Math.max(0, index - 1))}>← 上一题</button>{questionIndex < items.length - 1 ? <button className="primary-button" disabled={responses[items[questionIndex]?.item_ref] === undefined} onClick={() => setQuestionIndex((index) => Math.min(items.length - 1, index + 1))}>下一题 <span>→</span></button> : <button className="primary-button" disabled={answeredCount === 0} onClick={() => void submitAssessment()}>看见家庭理解 <span>→</span></button>}</div>
          </div>}
        </section>
      )}
      {view === "hypothesis" && hypothesis?.hypothesis && <section className="family-growth-panel"><span className="family-growth-step">一起看看</span><h2>{hypothesis.hypothesis.title ?? "我们这样理解你们现在的处境"}</h2><p className="family-growth-understanding">{hypothesis.hypothesis.statement ?? hypothesis.hypothesis.understanding}</p><p className="family-growth-muted">这只是一个可以修改的视角，不是诊断，也不是对孩子或家庭的结论。</p><div className="family-growth-actions"><button className="primary-button" onClick={() => void confirmUnderstanding()}>继续决定下一步</button><button className="secondary-button" onClick={() => setMessage("可以先保留不同意见，下一步仍然可以修改。")}>先保留不同意见</button></div></section>}
      {view === "draft" && draft && <section className="family-growth-panel"><span className="family-growth-step">给这个家的理解</span><h2>这段话，像你们的真实情况吗？</h2>{draftEditMode ? <textarea aria-label="修改这段理解" value={draftEditText} onChange={(event) => setDraftEditText(event.target.value)} /> : <p className="family-growth-understanding">{draft.understanding}</p>}<div className="family-growth-next"><strong>可以先从这里开始</strong><p>{draft.nextStep}</p></div><div className="family-growth-draft-details"><p className="family-growth-muted">你们可以修改、暂停或不同意。家庭的决定始终由家人自己做。</p><details><summary>看看依据和边界</summary><ul>{draft.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul></details></div><div className="family-growth-actions">{draftEditMode ? <><button className="primary-button" disabled={!draftEditText.trim()} onClick={() => void rewriteDraft()}>保存这次修改</button><button className="secondary-button" onClick={() => setDraftEditMode(false)}>先不修改</button></> : <><button className="primary-button" onClick={() => void acceptDraft()}>继续决定下一步</button><button className="secondary-button" onClick={() => setDraftEditMode(true)}>修改这段话</button><button className="secondary-button" onClick={() => setMessage("已先放一放，之后可以回来继续。")}>先放一放</button></>}</div></section>}
      {view === "path" && growthPath && <section className="family-growth-panel">
        <span className="family-growth-step">决定下一步</span>
        {growthPath.status === "DRAFT" ? <>
          <h2>接下来，家庭可以共同走向哪里</h2>
          <p className="family-growth-understanding">{growthPath.next_step}</p>
          <ol className="family-growth-path">{growthPath.path.map((item, index) => <li key={index}>
            {typeof item === "string" ? item : <>
              <strong>{item.title ?? item.capability_ref}</strong>
              {item.description && <span>{item.description}</span>}
            </>}
          </li>)}</ol>
          <p className="family-growth-muted">方向仍然是草案。家庭可以随时暂停、修改或重新开始。</p>
          {(growthPath.feedback_signals?.length ?? 0) > 0 && <p className="family-growth-muted">这份方向已参考你之前的反馈。</p>}
        </> : <>
          <h2>{growthPath.status === "REJECTED" ? "这份理解已被拒绝" : growthPath.status === "REVIEW_REQUIRED" ? "这份方向正在等待人工复核" : growthPath.status === "DEFERRED" ? "这份方向已暂缓" : "暂时还不能形成成长方向"}</h2>
          <p className="family-growth-understanding">{growthPath.status === "REJECTED" ? "家庭可以重新表达需要，再从新的草案开始。" : growthPath.status === "REVIEW_REQUIRED" ? "请等待人工支持完成复核。" : growthPath.status === "DEFERRED" ? "家庭可以稍后回到这份草案继续处理。" : "当前草案没有足够内容形成可展示的路径。"}</p>
        </>}
      </section>}
      <p className="family-growth-message" aria-live="polite">{message}</p>
    </main>
  );
}

function AssessmentItemView({ item, value, onChange }: { item: AssessmentItem; value: string | boolean | undefined; onChange: (value: string | boolean) => void }) {
  const labels: Record<string, string> = { FOCUS: "最近最想一起改善什么？", FAMILY_STRUCTURE: "现在的家庭陪伴方式更接近哪一种？", CHILD_GENDER: "孩子希望如何被称呼？" };
  const title = labels[item.item_ref] ?? (item.item_ref.includes("LEARNING_HABITS") ? "写作业或学习时，最近的情况是？" : item.item_ref.includes("PARENT_CHILD_COMMUNICATION") ? "你们最近沟通时，通常会发生什么？" : item.item_ref.includes("SELF_REGULATION") ? "孩子开始和完成事情时，通常是？" : item.item_ref.includes("DEVICE_USE") ? "关于设备使用，最近的情况是？" : item.item_ref.includes("EMOTION") ? "情绪起来时，最近的情况是？" : "最近的情况是？");
  const options: Record<string, string> = { LEARNING_HABITS: "学习习惯", EMOTION_REGULATION: "情绪调节", PARENT_CHILD_COMMUNICATION: "亲子沟通", DEVICE_USE_CONTEXT: "设备使用", SELF_REGULATION: "自我管理", often: "经常", sometimes: "有时", rarely: "很少", not_sure: "说不清", TWO_PARENT: "两位家长共同陪伴", SINGLE_PARENT: "一位家长陪伴", BLENDED: "重组家庭", PREFER_NOT_TO_SAY: "暂时不想说", BOY: "男孩", GIRL: "女孩", SELF_DESCRIBED: "孩子自己的称呼" };
  return <fieldset className="family-growth-item"><legend>{title}</legend>{item.response_type === "BOOLEAN" ? <div className="family-growth-choice"><button type="button" className={value === true ? "selected" : ""} onClick={() => onChange(true)}>是</button><button type="button" className={value === false ? "selected" : ""} onClick={() => onChange(false)}>不是</button></div> : item.response_type === "SINGLE_CHOICE" ? <div className="family-growth-choice">{(item.options ?? []).map((option) => <button type="button" className={value === option ? "selected" : ""} onClick={() => onChange(option)} key={option}>{options[option] ?? option}</button>)}</div> : <textarea aria-label={item.item_ref} value={typeof value === "string" ? value : ""} onChange={(event) => onChange(event.target.value)} placeholder="用你自己的话说说最近发生了什么" />}</fieldset>;
}
