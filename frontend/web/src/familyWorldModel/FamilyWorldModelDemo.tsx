import { useState } from "react";
import {
  FamilyWorldModelApiClient,
  type BeliefState,
  type StatementInput,
  type WorldStateAtom,
  type WorldStateConflict,
  type WorldStateUnknown,
} from "./client";

type Props = { client?: FamilyWorldModelApiClient };

const FAMILY_ID = "demo-family-1";
const PREDICATE = "child.parent_communication";
const SUBJECT_IDS = ["child-1", "mother-1", "father-1"];

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() || undefined;
const defaultClient = new FamilyWorldModelApiClient({ baseUrl: apiBaseUrl });

// Plain-language attribution for each family voice. The underlying request
// payload still sends the real speaker/epistemic_kind values the backend
// expects — this is presentation only.
const SPEAKER_LABEL: Record<string, string> = {
  mother: "妈妈",
  father: "爸爸",
  child: "孩子",
};

/** One family member's own words. Rendered plainly — no enum badge, just who said it. */
function VoiceCard({ atom }: { atom: WorldStateAtom }) {
  const speakerLabel = SPEAKER_LABEL[atom.asserted_by] ?? atom.asserted_by;
  return (
    <div className="fwm-voice-card">
      <div className="fwm-voice-head">{speakerLabel}</div>
      <p className="fwm-voice-text">{atom.value_ref}</p>
    </div>
  );
}

/** The AI's own tentative read — always visually soft/dashed so it never reads as a verdict. */
function TentativeReadCard({ atom }: { atom: WorldStateAtom }) {
  return (
    <div className="fwm-tentative-card">
      <div className="fwm-tentative-head">AI 的初步理解 · 还不确定</div>
      <p className="fwm-tentative-text">{atom.value_ref}</p>
    </div>
  );
}

function describeDifference(conflict: WorldStateConflict, atoms: WorldStateAtom[]): string {
  const names = conflict.atom_ids
    .map((id) => atoms.find((a) => a.atom_id === id))
    .filter((a): a is WorldStateAtom => Boolean(a))
    .map((a) => SPEAKER_LABEL[a.asserted_by] ?? a.asserted_by);
  const unique = Array.from(new Set(names));
  if (unique.length >= 2) {
    return `${unique.join("和")}对这件事的感受不太一样。`;
  }
  return "家里人对这件事的感受不太一样。";
}

export function FamilyWorldModelDemo({ client = defaultClient }: Props) {
  const [motherText, setMotherText] = useState(
    "我感觉孩子最近都不太愿意跟我们说心里话，一有话题就躲开。",
  );
  const [childText, setChildText] = useState(
    "我是愿意说的，但每次一开口就先被批评，所以后来就不太想说了。",
  );
  const [fatherText, setFatherText] = useState(
    "最近晚饭时间明显安静了很多，之前一家人会聊学校的事，现在基本没人开口。",
  );

  const [submitLoading, setSubmitLoading] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [atoms, setAtoms] = useState<WorldStateAtom[]>([]);
  const [conflicts, setConflicts] = useState<WorldStateConflict[]>([]);
  const [submitted, setSubmitted] = useState(false);

  const [readLoading, setReadLoading] = useState(false);
  const [readUnavailable, setReadUnavailable] = useState(false);
  const [hypothesis, setHypothesis] = useState<WorldStateAtom | null>(null);
  const [readAttempted, setReadAttempted] = useState(false);

  const [questionLoading, setQuestionLoading] = useState(false);
  const [questionUnavailable, setQuestionUnavailable] = useState(false);
  const [unknown, setUnknown] = useState<WorldStateUnknown | null>(null);
  const [questionAsked, setQuestionAsked] = useState(false);

  const [answerText, setAnswerText] = useState(
    "其他事情孩子都愿意聊，主要是一提到学校的成绩和作业，她就会紧张、不想说了。",
  );
  const [answerLoading, setAnswerLoading] = useState(false);
  const [answerError, setAnswerError] = useState<string | null>(null);
  const [answered, setAnswered] = useState(false);

  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [beliefState, setBeliefState] = useState<BeliefState | null>(null);

  async function submitStatements() {
    setSubmitLoading(true);
    setSubmitError(null);
    try {
      const statements: StatementInput[] = [
        {
          speaker: "mother",
          epistemic_kind: "PERSPECTIVE",
          predicate: PREDICATE,
          text: motherText,
          subject_ids: SUBJECT_IDS,
        },
        {
          speaker: "child",
          epistemic_kind: "SELF_REPORT",
          predicate: PREDICATE,
          text: childText,
          subject_ids: SUBJECT_IDS,
        },
        {
          speaker: "father",
          epistemic_kind: "OBSERVATION",
          predicate: PREDICATE,
          text: fatherText,
          subject_ids: SUBJECT_IDS,
        },
      ];
      const result = await client.submitStatements(FAMILY_ID, statements);
      setAtoms(result.atoms);
      setConflicts(result.conflicts);
      setSubmitted(true);
      // Kick off the AI's tentative read right away, as the natural next
      // beat in the conversation rather than a separate manual step.
      void requestTentativeRead(result.atoms);
    } catch {
      setSubmitError("这次没能提交成功，要不要再试一次？");
    } finally {
      setSubmitLoading(false);
    }
  }

  async function requestTentativeRead(evidenceAtoms: WorldStateAtom[]) {
    setReadLoading(true);
    setReadUnavailable(false);
    try {
      const result = await client.createHypothesis(FAMILY_ID, {
        subject_ids: SUBJECT_IDS,
        target_predicate: PREDICATE,
        evidence_atom_ids: evidenceAtoms.map((atom) => atom.atom_id),
      });
      setHypothesis(result.hypothesis);
      void requestClarifyingQuestion(result.hypothesis);
    } catch {
      // Whether the model isn't configured (503) or was declined (502), the
      // parent should see the same calm message and the flow keeps going —
      // this step is a bonus, never a dead end.
      setReadUnavailable(true);
    } finally {
      setReadLoading(false);
      setReadAttempted(true);
    }
  }

  async function requestClarifyingQuestion(hypothesisAtom: WorldStateAtom) {
    setQuestionLoading(true);
    setQuestionUnavailable(false);
    try {
      const result = await client.createUnknown(FAMILY_ID, {
        subject_ids: SUBJECT_IDS,
        hypothesis_atom_ids: [hypothesisAtom.atom_id],
        allowed_target_predicates: [PREDICATE, "child.school_related_stress"],
      });
      // result.unknown === null means the AI already effectively asked an
      // equivalent question — treated as "already understood", not an error.
      setUnknown(result.unknown);
    } catch {
      setQuestionUnavailable(true);
    } finally {
      setQuestionLoading(false);
      setQuestionAsked(true);
    }
  }

  async function submitAnswer() {
    if (!unknown) return;
    setAnswerLoading(true);
    setAnswerError(null);
    try {
      await client.resolveUnknown(FAMILY_ID, unknown.unknown_id, {
        speaker: "mother",
        epistemic_kind: "OTHER_REPORT",
        predicate: PREDICATE,
        text: answerText,
        subject_ids: SUBJECT_IDS,
      });
      setAnswered(true);
      void loadSummary();
    } catch {
      setAnswerError("这条回答刚刚没有保存成功，要不要再发一次？");
    } finally {
      setAnswerLoading(false);
    }
  }

  async function loadSummary() {
    setSummaryLoading(true);
    setSummaryError(null);
    try {
      const result = await client.getBeliefState(FAMILY_ID, SUBJECT_IDS);
      setBeliefState(result);
    } catch {
      setSummaryError("现在没能读取到最新的理解，稍后可以再看看。");
    } finally {
      setSummaryLoading(false);
    }
  }

  const unresolvedDifferences = beliefState?.effective_open_conflicts ?? conflicts;
  const showFollowUpStep = submitted && (readAttempted || readLoading);

  return (
    <main className="fwm-shell">
      <header className="fwm-header">
        <span className="fwm-brand">AiFamily</span>
        <h1>说说最近让你担心的事</h1>
        <p className="fwm-intro">
          把家里人各自的感受写下来，我会陪你一起看看，孩子和大人看到的可能不太一样，
          也会试着帮你理清楚接下来可以怎么问、怎么想。
        </p>
      </header>

      {/* Opening: the parent describes the situation from three natural angles */}
      <section className="fwm-turn">
        <div className="fwm-statement-grid">
          <label>
            <span>你怎么看这件事</span>
            <textarea value={motherText} onChange={(event) => setMotherText(event.target.value)} />
          </label>
          <label>
            <span>孩子怎么说</span>
            <textarea value={childText} onChange={(event) => setChildText(event.target.value)} />
          </label>
          <label>
            <span>其他家人观察到什么</span>
            <textarea value={fatherText} onChange={(event) => setFatherText(event.target.value)} />
          </label>
        </div>
        <button className="fwm-primary-button" disabled={submitLoading} onClick={() => void submitStatements()}>
          {submitLoading ? "正在整理…" : "说给我听"}
        </button>
        {submitError && <p className="fwm-error">{submitError}</p>}
      </section>

      {/* What the family is seeing differently */}
      {submitted && (
        <section className="fwm-turn">
          <h2 className="fwm-turn-title">我听到的</h2>
          <div className="fwm-voice-list">
            {atoms.map((atom) => (
              <VoiceCard atom={atom} key={atom.atom_id} />
            ))}
          </div>
          {unresolvedDifferences.length > 0 ? (
            <div className="fwm-notice">
              {unresolvedDifferences.map((conflict) => (
                <p key={conflict.conflict_id}>{describeDifference(conflict, atoms)}</p>
              ))}
            </div>
          ) : (
            <p className="fwm-muted">大家的感受基本是一致的。</p>
          )}
        </section>
      )}

      {/* AI's tentative read */}
      {showFollowUpStep && (
        <section className="fwm-turn">
          <h2 className="fwm-turn-title">我的初步理解</h2>
          {readLoading && <p className="fwm-muted">正在琢磨这件事…</p>}
          {readUnavailable && (
            <p className="fwm-muted">现在还没办法给出判断，不过我们可以继续往下看看。</p>
          )}
          {hypothesis && <TentativeReadCard atom={hypothesis} />}
        </section>
      )}

      {/* Clarifying question */}
      {questionAsked && (
        <section className="fwm-turn">
          <h2 className="fwm-turn-title">我想再确认一下</h2>
          {questionLoading && <p className="fwm-muted">让我想想该怎么问…</p>}
          {questionUnavailable && (
            <p className="fwm-muted">这一步现在问不出更具体的问题，我们可以先看看已经了解到的内容。</p>
          )}
          {unknown ? (
            <>
              <p className="fwm-question-text">{unknown.question}</p>
              <label>
                <span>你的回答</span>
                <textarea value={answerText} onChange={(event) => setAnswerText(event.target.value)} />
              </label>
              <button
                className="fwm-primary-button"
                disabled={answerLoading || answered}
                onClick={() => void submitAnswer()}
              >
                {answerLoading ? "正在记录…" : answered ? "已经收到啦" : "回复"}
              </button>
              {answerError && <p className="fwm-error">{answerError}</p>}
            </>
          ) : (
            !questionLoading &&
            !questionUnavailable && (
              <p className="fwm-muted">这个问题我已经了解过了，我们的理解不用重复确认。</p>
            )
          )}
        </section>
      )}

      {/* Updated understanding */}
      {(answered || (questionAsked && !unknown && !questionLoading)) && (
        <section className="fwm-turn">
          <h2 className="fwm-turn-title">现在我们的理解是……</h2>
          {summaryLoading && <p className="fwm-muted">正在整理最新的理解…</p>}
          {summaryError && <p className="fwm-error">{summaryError}</p>}
          {beliefState && (
            <div className="fwm-summary">
              {beliefState.perspectives.length > 0 && (
                <p>孩子和家人各自的感受，我都记住了，会在后面持续参考。</p>
              )}
              {beliefState.hypotheses.length > 0 && (
                <p>我对这件事有了一个更清楚一点的理解，但仍会随着新的信息继续调整，不会当作最终结论。</p>
              )}
              {beliefState.effective_open_unknowns.length > 0 ? (
                <p>还有一些地方需要再多了解一下，我会在合适的时候继续问。</p>
              ) : (
                <p>目前没有明显还悬而未决的问题。</p>
              )}
              {beliefState.effective_open_conflicts.length > 0 ? (
                <p>家里人对这件事的感受还没有完全对齐，这很正常，可以慢慢聊。</p>
              ) : (
                <p>家里人对这件事的感受，现在看起来比较一致了。</p>
              )}
            </div>
          )}
          {!beliefState && !summaryLoading && !summaryError && (
            <button className="fwm-secondary-button" onClick={() => void loadSummary()}>
              看看现在的理解
            </button>
          )}
        </section>
      )}
    </main>
  );
}
