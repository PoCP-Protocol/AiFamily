import { useEffect, useState } from "react";

type Question = {
  question_ref: string;
  session_ref: string;
  text: string;
  status: "PENDING" | "APPROVED" | "REJECTED";
  source: "SANDBOX_SYNTHETIC";
  fixture_only: true;
};

type Props = { interactionBaseUrl?: string; controlBaseUrl?: string };

const MODERATOR_HEADERS = {
  "Content-Type": "application/json",
  "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
  "X-Fixture-Only": "true",
  "X-Tenant-Id": "tenant.synthetic.alpha",
  "X-Family-Id": "family.synthetic.alpha",
  "X-Actor-Id": "actor.synthetic.moderator",
  "X-Actor-Role": "HUMAN_MODERATOR",
};
const CONTENT_REVIEWER_HEADERS = {
  ...MODERATOR_HEADERS,
  "X-Actor-Id": "actor.synthetic.content-reviewer",
  "X-Actor-Role": "CONTENT_REVIEWER",
};

export function LiveModeratorConsole({ interactionBaseUrl, controlBaseUrl }: Props) {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "missing" | "error">(
    interactionBaseUrl ? "loading" : "missing",
  );

  useEffect(() => {
    if (!interactionBaseUrl) return;
    void loadQuestions();
  }, [controlBaseUrl, interactionBaseUrl]);

  const pending = questions.filter((question) => question.status === "PENDING");

  return (
    <section className="live-ops-shell" aria-labelledby="live-ops-heading">
      <header className="live-ops-heading">
        <div>
          <p className="live-kicker">小橘灯专家工作台</p>
          <h2 id="live-ops-heading">直播提问审核</h2>
          <p>成人问题先由人工判断，再决定是否进入直播讨论区。</p>
        </div>
        <span>{pending.length} 条待审核</span>
      </header>

      {state === "loading" ? <p className="live-ops-state">正在读取审核队列…</p> : null}
      {state === "missing" ? <p className="live-ops-state">审核服务暂不可用。</p> : null}
      {state === "error" ? <p className="live-ops-state">审核队列读取失败，请稍后重试。</p> : null}
      {state === "ready" && pending.length === 0 ? (
        <div className="live-ops-empty"><strong>当前没有待审核问题</strong><p>新问题提交后会出现在这里。</p></div>
      ) : null}

      <div className="live-ops-list">
        {pending.map((question) => (
          <article className="live-ops-card" key={question.question_ref}>
            <div>
              <span>家长提问</span>
              <strong>{question.text}</strong>
              <small>{question.session_ref} · 等待人工判断 · 不会自动展示</small>
            </div>
            <div className="live-ops-actions">
              <button type="button" onClick={() => void decide(question, "APPROVE")}>批准展示</button>
              <button className="live-ops-reject" type="button" onClick={() => void decide(question, "REJECT")}>不予展示</button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );

  async function loadQuestions() {
    if (!interactionBaseUrl) return;
    try {
      const sessionRefs = controlBaseUrl
        ? await loadActiveSessionRefs(controlBaseUrl)
        : ["media.synthetic.1"];
      const responses = await Promise.all(sessionRefs.map((sessionRef) => fetch(
        `${interactionBaseUrl}/sandbox/live/sessions/${sessionRef}/questions`,
        { cache: "no-store", headers: MODERATOR_HEADERS },
      )));
      if (responses.some((response) => !response.ok)) throw new Error("queue failed");
      const result = (await Promise.all(responses.map(
        (response) => response.json() as Promise<Question[]>,
      ))).flat();
      setQuestions(result.filter(
        (question) =>
          question.fixture_only === true && question.source === "SANDBOX_SYNTHETIC",
      ));
      setState("ready");
    } catch {
      setState("error");
    }
  }

  async function decide(question: Question, action: "APPROVE" | "REJECT") {
    if (!interactionBaseUrl) return;
    try {
      const response = await fetch(
        `${interactionBaseUrl}/sandbox/moderation/questions/${question.question_ref}/decision`,
        {
          method: "POST",
          headers: MODERATOR_HEADERS,
          body: JSON.stringify({
            decision_key: `decision.${question.question_ref}.${action.toLowerCase()}`,
            action,
            reason: action === "APPROVE" ? "人工审核确认可展示" : "人工审核决定不展示",
          }),
        },
      );
      if (!response.ok) throw new Error("decision failed");
      const decided = (await response.json()) as Question;
      setQuestions((current) => current.map((item) => item.question_ref === decided.question_ref ? decided : item));
    } catch {
      setState("error");
    }
  }
}

async function loadActiveSessionRefs(controlBaseUrl: string): Promise<string[]> {
  const response = await fetch(`${controlBaseUrl}/sandbox/live-control/operator/sessions`, {
    cache: "no-store",
    headers: CONTENT_REVIEWER_HEADERS,
  });
  if (!response.ok) throw new Error("session listing failed");
  const sessions = await response.json() as Array<Record<string, unknown>>;
  if (!Array.isArray(sessions)) throw new Error("invalid session listing");
  return sessions
    .filter(
      (session) =>
        session.source === "SANDBOX_SYNTHETIC" &&
        session.fixture_only === true &&
        session.approval_status === "APPROVED" &&
        ["SCHEDULED", "LIVE"].includes(String(session.status)) &&
        typeof session.session_ref === "string",
    )
    .map((session) => String(session.session_ref));
}
