import { useEffect, useMemo, useState } from "react";
import { HttpExperienceApiClient } from "../api/httpClient";
import type { ExperienceApiClient } from "../api/client";
import {
  FamilyGrowthApiClient,
  FamilyGrowthApiError,
  type AssessmentItem,
  type AssessmentProjection,
  type GrowthHypothesisProjection,
} from "./client";

type Props = {
  familyId?: string;
  growthClient?: FamilyGrowthApiClient;
  experienceClient?: ExperienceApiClient;
};

type View = "loading" | "assessment" | "hypothesis" | "draft" | "path" | "error";

const newId = (prefix: string) =>
  `${prefix}-${typeof crypto.randomUUID === "function" ? crypto.randomUUID() : Date.now()}`;

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL as string | undefined;
const apiToken = import.meta.env.VITE_API_TOKEN as string | undefined;

export function FamilyGrowthExperience({
  familyId = import.meta.env.VITE_FAMILY_ID || "family-current",
  growthClient = new FamilyGrowthApiClient({ baseUrl: apiBaseUrl, accessToken: apiToken }),
  experienceClient = new HttpExperienceApiClient({ baseUrl: apiBaseUrl, accessToken: apiToken }),
}: Props) {
  const [view, setView] = useState<View>("loading");
  const [assessment, setAssessment] = useState<AssessmentProjection | null>(null);
  const [hypothesis, setHypothesis] = useState<GrowthHypothesisProjection | null>(null);
  const [responses, setResponses] = useState<Record<string, string | boolean>>({});
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [draft, setDraft] = useState<{ understanding: string; nextStep: string } | null>(null);
  const [growthPath, setGrowthPath] = useState<{ next_step: string | null; path: unknown[] } | null>(null);
  const [message, setMessage] = useState("");

  const subject = assessment?.subjects?.[0];
  const items: AssessmentItem[] = assessment?.tool?.items ?? [];
  const answeredCount = useMemo(() => Object.keys(responses).length, [responses]);

  useEffect(() => {
    void refreshAssessment();
  }, []);

  async function refreshAssessment() {
    setView("loading");
    try {
      const result = await growthClient.getAssessment(familyId);
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
      const result = await growthClient.startAssessment(
        familyId,
        { subject_person_id: subject.person_id, tool_ref: assessment.tool.tool_ref },
        newId("assessment-start"),
      );
      setSessionId(result.session_id);
      setResponses({});
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
        await growthClient.saveAssessmentResponse(
          familyId,
          sessionId,
          { item_ref: item.item_ref, response_type: item.response_type, response_value: responses[item.item_ref] },
          newId(`assessment-response-${item.item_ref}`),
        );
      }
      await growthClient.submitAssessment(familyId, sessionId, newId("assessment-submit"));
      const next = await growthClient.getGrowthHypothesis(familyId);
      setHypothesis(next);
      setView("hypothesis");
      setMessage("这是 AI 对家庭现状的理解草案，请先看看它是否说中了你们。");
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
      await growthClient.decideGrowthHypothesis(
        familyId,
        { assessment_session_id: sessionId, hypothesis_ref: value.hypothesis_ref, decision_type: "CONFIRM" },
        newId("hypothesis-confirm"),
      );
      const nextRunId = newId("family-understanding");
      setRunId(nextRunId);
      const result = await experienceClient.createDraft(
        {
          run_id: nextRunId,
          use_case: "family_understanding_draft",
          prompt_version: "family-companion.v1",
          schema_version: "family-experience-draft.v1",
          data_class: "FAMILY_PRIVATE_TEXT",
          context_snapshot_ref: "server-owned",
          payload: {
            expression: value.statement ?? value.understanding ?? value.title ?? "请理解这个家庭当前的成长需要。",
            family_need_id: needId,
            path_id: pathId,
          },
          input_refs: value.evidence_refs ?? [],
          media_inputs: [],
          scope: {
            tenant_id: "server-owned",
            region_id: "CN",
            family_id: familyId,
            subject_ids: subject ? [subject.person_id] : [],
            purpose: "family_understanding_draft",
            consent_version: "server-owned",
            consent_granted: true,
            locale: "zh-CN",
          },
        },
        newId("experience-draft"),
      );
      setDraft({ understanding: result.output.understanding, nextStep: result.output.next_step });
      setView("draft");
      setMessage("这是一份 AI 理解草案。你可以确认、修改或暂缓，不会自动成为家庭事实。");
    } catch (error) {
      fail(error, "AI 理解草案暂时无法生成。");
    }
  }

  async function acceptDraft() {
    if (!runId) return;
    try {
      await experienceClient.decide({ run_id: runId, decision: "confirm" }, newId("draft-confirm"));
      const result = await growthClient.getGrowthPath(familyId, runId);
      setGrowthPath(result);
      setView("path");
      setMessage("成长方向已经准备好，请把它当作共同讨论的起点。");
    } catch (error) {
      fail(error, "成长方向暂时无法读取。");
    }
  }

  function fail(error: unknown, fallback: string) {
    setView("error");
    setMessage(error instanceof FamilyGrowthApiError ? `${fallback}（${error.status}）` : fallback);
  }

  if (view === "loading") return <main className="family-growth-shell"><p>正在打开家庭成长空间…</p></main>;
  if (view === "error") {
    return <main className="family-growth-shell"><p className="family-growth-error">{message}</p><button className="primary-button" onClick={() => void refreshAssessment()}>重新打开</button></main>;
  }

  return (
    <main className="family-growth-shell">
      <header className="family-growth-header"><span className="family-growth-brand">AiFamily</span><span>家庭成长空间</span></header>
      <section className="family-growth-hero">
        <p className="family-growth-kicker">给家长的第一份服务</p>
        <h1>先理解这个家，<br />再一起往前走。</h1>
        <p>这不是给家庭打分，而是把你们正在经历的事情，整理成可以共同看见、共同决定的理解。</p>
      </section>
      <section className="family-growth-progress" aria-label="家庭成长流程">
        {[["01", "理解家庭"], ["02", "AI 草案"], ["03", "成长方向"]].map(([number, label], index) => (
          <div className={index <= (view === "assessment" ? 0 : view === "hypothesis" ? 1 : 2) ? "active" : ""} key={number}><b>{number}</b><span>{label}</span></div>
        ))}
      </section>
      {view === "assessment" && (
        <section className="family-growth-panel">
          <div className="family-growth-panel-heading"><div><span className="family-growth-step">第一步</span><h2>从几个维度，看见家庭现在的状态</h2></div><span className="family-growth-count">{answeredCount}/{items.length} 已完成</span></div>
          {subject ? <p className="family-growth-subject">本次理解对象：{subject.display_name}</p> : <p className="family-growth-error">当前没有可用的家庭成员授权。</p>}
          {!sessionId ? <button className="primary-button" disabled={!subject || !assessment?.tool} onClick={() => void startAssessment()}>开始家庭测评</button> : <div className="family-growth-items">{items.map((item) => <AssessmentItemView item={item} value={responses[item.item_ref]} onChange={(value) => setResponses((current) => ({ ...current, [item.item_ref]: value }))} key={item.item_ref} />)}<button className="primary-button" disabled={answeredCount === 0} onClick={() => void submitAssessment()}>提交并看见家庭理解</button></div>}
        </section>
      )}
      {view === "hypothesis" && hypothesis?.hypothesis && <section className="family-growth-panel"><span className="family-growth-step">第二步 · AI 理解草案</span><h2>{hypothesis.hypothesis.title ?? "我们这样理解你们现在的处境"}</h2><p className="family-growth-understanding">{hypothesis.hypothesis.statement ?? hypothesis.hypothesis.understanding}</p><p className="family-growth-muted">这是一种可修改的视角，不是诊断，也不是对孩子或家庭的结论。</p><div className="family-growth-actions"><button className="primary-button" onClick={() => void confirmUnderstanding()}>确认这份理解，继续往前</button><button className="secondary-button" onClick={() => setMessage("你可以先保留不同意见，后续会支持修订。")}>我想先修改</button></div></section>}
      {view === "draft" && draft && <section className="family-growth-panel"><span className="family-growth-step">AI 理解草案 · 可确认</span><h2>这是给这个家庭的专属理解</h2><p className="family-growth-understanding">{draft.understanding}</p><div className="family-growth-next"><strong>接下来可以从这里开始</strong><p>{draft.nextStep}</p></div><div className="family-growth-actions"><button className="primary-button" onClick={() => void acceptDraft()}>确认并查看成长方向</button><button className="secondary-button" onClick={() => setMessage("已保留这份草案，你可以稍后继续。")}>暂缓</button></div></section>}
      {view === "path" && growthPath && <section className="family-growth-panel"><span className="family-growth-step">第三步 · 成长方向</span><h2>接下来，家庭可以共同走向哪里</h2><p className="family-growth-understanding">{growthPath.next_step ?? "这份方向还在等待进一步共同确认。"}</p><ol className="family-growth-path">{growthPath.path.map((item, index) => <li key={index}>{typeof item === "string" ? item : JSON.stringify(item)}</li>)}</ol><p className="family-growth-muted">方向仍然是草案。家庭可以随时暂停、修改或重新开始。</p></section>}
      <p className="family-growth-message" aria-live="polite">{message}</p>
    </main>
  );
}

function AssessmentItemView({ item, value, onChange }: { item: AssessmentItem; value: string | boolean | undefined; onChange: (value: string | boolean) => void }) {
  return <fieldset className="family-growth-item"><legend>{item.item_ref}</legend>{item.response_type === "BOOLEAN" ? <div className="family-growth-choice"><button type="button" className={value === true ? "selected" : ""} onClick={() => onChange(true)}>是</button><button type="button" className={value === false ? "selected" : ""} onClick={() => onChange(false)}>不是</button></div> : item.response_type === "SINGLE_CHOICE" ? <div className="family-growth-choice">{(item.options ?? []).map((option) => <button type="button" className={value === option ? "selected" : ""} onClick={() => onChange(option)} key={option}>{option}</button>)}</div> : <textarea aria-label={item.item_ref} value={typeof value === "string" ? value : ""} onChange={(event) => onChange(event.target.value)} placeholder="用你自己的话说说最近发生了什么" />}</fieldset>;
}
