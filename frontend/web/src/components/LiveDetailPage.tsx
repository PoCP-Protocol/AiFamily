import { FormEvent, useEffect, useRef, useState } from "react";
import {
  resolveLiveControlBaseUrl,
  type LiveRecord,
  type MediaPlaybackState,
} from "../live/liveCatalog";
import { LiveReplayKnowledge } from "./LiveReplayKnowledge";

type Props = {
  record: LiveRecord;
  interactionBaseUrl?: string;
  interactionWsUrl?: string;
  incidentBaseUrl?: string;
  replayBaseUrl?: string;
  replayKnowledgeBaseUrl?: string;
  commerceBaseUrl?: string;
  controlBaseUrl?: string;
  onBack: () => void;
};

type LiveQuestion = {
  question_ref: string;
  session_ref: string;
  text: string;
  status: "PENDING" | "APPROVED" | "REJECTED";
  source: "SANDBOX_SYNTHETIC";
  fixture_only: true;
};

type SurfaceState = "WAITING_AUTHORIZATION" | "LOADING" | MediaPlaybackState | "FAILED";
type ReplayState =
  | "idle"
  | "restoring"
  | "unlocking"
  | "unlocked"
  | "loading"
  | "available"
  | "revoking"
  | "revoked"
  | "deleting"
  | "deleted"
  | "error";

type ReplayView = {
  session_ref: string;
  state: "AVAILABLE" | "DELETED";
  playback_url: string | null;
  source: "SANDBOX_SYNTHETIC";
  fixture_only: true;
};

type DeletionView = {
  deletion_ref: string;
  session_ref: string;
  affected_refs: string[];
  state: "DELETED";
  source: "SANDBOX_SYNTHETIC";
  fixture_only: true;
};

type CommerceEvidence = {
  source: "SANDBOX_SYNTHETIC";
  fixture_only: true;
  external_effect: false;
};

type MediaPurchase = CommerceEvidence & {
  purchase_ref: string;
  track: "MEDIA_ENTITLEMENT";
};

type MediaBalance = CommerceEvidence & {
  purchase_ref: string;
  cash: number;
  settlement: number;
  entitlement: "ACTIVE" | "REVOKED";
};

type RegistrationState =
  | "missing"
  | "idle"
  | "registering"
  | "confirmed"
  | "cancelling"
  | "cancelled"
  | "error";

type RegistrationView = {
  registration_ref: string;
  session_ref: string;
  tenant_id: string;
  family_id: string;
  guardian_id: string;
  consent_ref: string;
  status: "CONFIRMED" | "CANCELLED";
};

type RegistrationReceipt = {
  registration: RegistrationView;
  source: "SANDBOX_SYNTHETIC";
  fixture_only: true;
  external_effect: false;
};

type DirectRegistrationReceipt = RegistrationView & {
  source: "SANDBOX_SYNTHETIC";
  fixture_only: true;
  external_effect: false;
};

const SANDBOX_DIAGNOSTIC_MARKERS =
  "SANDBOX_SYNTHETIC fixture_only DEV_ONLY LOCKED WAITING_AUTHORIZATION 问题搜索 直播中 已结束 / 回看受限 NO_MEDIA MEDIA_READY PLAYBACK_AUTHORIZED SCHEDULED ENDED";
const SYNTHETIC_VIDEO_POSTER = `data:image/svg+xml,${encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#431407"/><stop offset=".55" stop-color="#9a3412"/><stop offset="1" stop-color="#f97316"/></linearGradient><radialGradient id="l"><stop stop-color="#fed7aa" stop-opacity=".75"/><stop offset="1" stop-color="#fb923c" stop-opacity="0"/></radialGradient></defs><rect width="1600" height="900" fill="url(#g)"/><circle cx="330" cy="220" r="280" fill="url(#l)"/><circle cx="800" cy="410" r="118" fill="#fff7ed" fill-opacity=".96"/><path d="M775 350v120l95-60z" fill="#c2410c"/><circle cx="1370" cy="120" r="220" fill="none" stroke="#fed7aa" stroke-opacity=".35" stroke-width="3"/><text x="800" y="650" fill="#fff7ed" text-anchor="middle" font-family="system-ui,sans-serif" font-size="72" font-weight="700">小橘灯直播</text><text x="800" y="720" fill="#fed7aa" text-anchor="middle" font-family="system-ui,sans-serif" font-size="34">合成演示封面 · 点击播放</text></svg>',
)}`;

const SYNTHETIC_ACTOR_HEADERS = {
  "Content-Type": "application/json",
  "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
  "X-Fixture-Only": "true",
  "X-Tenant-Id": "tenant.synthetic.alpha",
  "X-Family-Id": "family.synthetic.alpha",
  "X-Actor-Id": "actor.synthetic.adult",
  "X-Actor-Role": "ADULT_VIEWER",
};
const MEDIA_ENTITLEMENT_REF_KEY = "xiaojudeng.sandbox.media_entitlement.purchase_ref";

export function LiveDetailPage({
  record,
  interactionBaseUrl,
  interactionWsUrl,
  incidentBaseUrl,
  replayBaseUrl,
  replayKnowledgeBaseUrl,
  commerceBaseUrl,
  controlBaseUrl,
  onBack,
}: Props) {
  const playback = record.playback;
  const [surfaceState, setSurfaceState] = useState<SurfaceState>(
    playback?.state ?? "WAITING_AUTHORIZATION",
  );
  const [mediaUrl, setMediaUrl] = useState(playback ? playback.playback_url : "");
  const [questions, setQuestions] = useState<LiveQuestion[]>([]);
  const [questionText, setQuestionText] = useState("");
  const [questionState, setQuestionState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [realtimeState, setRealtimeState] = useState<"offline" | "connecting" | "live">("offline");
  const [incidentState, setIncidentState] = useState<"idle" | "sending" | "reported" | "error">("idle");
  const [replayState, setReplayState] = useState<ReplayState>("idle");
  const [replayUrl, setReplayUrl] = useState("");
  const [mediaEntitlementRef, setMediaEntitlementRef] = useState("");
  const [deletedRefs, setDeletedRefs] = useState<string[]>([]);
  const registrationApiBaseUrl = resolveRegistrationBaseUrl(controlBaseUrl);
  const [registrationState, setRegistrationState] = useState<RegistrationState>(
    registrationApiBaseUrl ? "idle" : "missing",
  );
  const [registrationRef, setRegistrationRef] = useState("");
  const hasStartedPlayback = useRef(false);
  const canRenderVideo =
    playback?.source === "synthetic" &&
    playback.fixture_only &&
    ["LIVE", "LOADING", "RESTARTED"].includes(surfaceState) &&
    isLocalPlaybackUrl(mediaUrl);
  const playbackMessage = getPlaybackMessage(surfaceState);
  const showAdultNextStep = ["ENDED", "STOPPED", "REVOKED"].includes(surfaceState);
  const sessionLabel = getEffectiveSessionLabel(record.status, surfaceState);
  const isLiveSession = sessionLabel === "直播中";
  const registrationEligible =
    record.source === "SANDBOX_SYNTHETIC" &&
    record.fixture_only === true &&
    record.approval_status === "APPROVED" &&
    record.expiry_state === "UNEXPIRED" &&
    record.status === "SCHEDULED" &&
    record.audience_scope === "FAMILY" &&
    record.family_visibility === "family-private";

  useEffect(() => {
    if (!interactionBaseUrl) return;
    const controller = new AbortController();
    void fetch(`${interactionBaseUrl}/sandbox/live/sessions/${record.session_ref}/questions`, {
      cache: "no-store",
      headers: SYNTHETIC_ACTOR_HEADERS,
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error("question read failed");
        return response.json() as Promise<LiveQuestion[]>;
      })
      .then((items) => setQuestions(items.filter((item) => item.fixture_only === true)))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) setQuestionState("error");
      });
    return () => controller.abort();
  }, [interactionBaseUrl, record.session_ref]);

  useEffect(() => {
    if (!interactionWsUrl) return;
    setRealtimeState("connecting");
    let socket: WebSocket;
    try {
      const url = new URL(
        `/ws/sandbox/live/sessions/${record.session_ref}/questions`,
        interactionWsUrl,
      );
      url.search = new URLSearchParams({
        source: "SANDBOX_SYNTHETIC",
        fixture_only: "true",
        tenant_id: "tenant.synthetic.alpha",
        family_id: "family.synthetic.alpha",
        actor_id: "actor.synthetic.adult",
        role: "ADULT_VIEWER",
      }).toString();
      socket = new WebSocket(url);
    } catch {
      setRealtimeState("offline");
      return;
    }
    socket.onopen = () => setRealtimeState("live");
    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(String(event.data)) as Record<string, unknown>;
        if (
          payload.source !== "SANDBOX_SYNTHETIC" ||
          payload.fixture_only !== true ||
          payload.external_effect !== false ||
          !["QUESTION_SUBMITTED", "QUESTION_REVIEWED"].includes(String(payload.type))
        ) return;
        const question = parseRealtimeQuestion(payload.question);
        setQuestions((current) => [
          ...current.filter((item) => item.question_ref !== question.question_ref),
          question,
        ]);
      } catch {
        // HTTP reload remains the source of truth after malformed realtime data.
      }
    };
    socket.onerror = () => setRealtimeState("offline");
    socket.onclose = () => setRealtimeState("offline");
    return () => socket.close();
  }, [interactionWsUrl, record.session_ref]);

  useEffect(() => {
    if (!commerceBaseUrl || !isLocalPlaybackUrl(commerceBaseUrl)) return;
    const storedRef = localStorage.getItem(MEDIA_ENTITLEMENT_REF_KEY);
    if (!storedRef) return;
    const controller = new AbortController();
    setReplayState("restoring");
    void loadMediaBalance(commerceBaseUrl, storedRef, controller.signal)
      .then((balance) => {
        setMediaEntitlementRef(storedRef);
        setReplayState(balance.entitlement === "ACTIVE" ? "unlocked" : "revoked");
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) setReplayState("error");
      });
    return () => controller.abort();
  }, [commerceBaseUrl]);

  return (
    <article className="live-detail-page" aria-labelledby="live-detail-heading">
      <div className="live-detail-header">
        <div>
          <button className="live-inline-back" type="button" onClick={onBack}>← 返回直播首页</button>
          <h3 id="live-detail-heading">{record.title}</h3>
          <p className="live-detail-expert">{record.speaker} · 适合{record.applicable_scope}</p>
        </div>
        <span className="live-status-badge">{sessionLabel}</span>
      </div>

      <div className="live-watch-layout">
        <section className="live-video-container" aria-labelledby="live-video-heading" data-playback-state={surfaceState}>
          {canRenderVideo ? (
            <div className="live-video-frame live-video-authorized">
            <h4 id="live-video-heading" className="visually-hidden">视频播放区域</h4>
            <video
              aria-label="小橘灯合成视频播放区域"
              controls
              playsInline
              poster={SYNTHETIC_VIDEO_POSTER}
              preload="none"
              src={mediaUrl}
              onError={() => {
                if (hasStartedPlayback.current) setSurfaceState("FAILED");
              }}
              onLoadStart={() => {
                if (hasStartedPlayback.current) setSurfaceState("LOADING");
              }}
              onLoadedData={() => setSurfaceState("LIVE")}
              onPlay={() => {
                hasStartedPlayback.current = true;
              }}
              onPlaying={() => {
                hasStartedPlayback.current = true;
                setSurfaceState("LIVE");
              }}
              onStalled={() => {
                if (hasStartedPlayback.current) setSurfaceState("DISCONNECTED");
              }}
              onWaiting={() => {
                if (hasStartedPlayback.current) setSurfaceState("DISCONNECTED");
              }}
            />
            <div className="live-video-caption" role="status" aria-live="polite">
              <span className="live-video-state">{getPlaybackLabel(surfaceState)}</span>
              <p>{playbackMessage}</p>
            </div>
            </div>
          ) : (
            <div className="live-video-frame" role="status">
            <span className="live-video-placeholder-icon" aria-hidden="true">▶</span>
            <h4 id="live-video-heading">
              {surfaceState === "WAITING_AUTHORIZATION" ? "视频暂不可用" : playbackMessage}
            </h4>
            {surfaceState !== "WAITING_AUTHORIZATION"
              ? <p>{getRecoveryHint(surfaceState)}</p>
              : <p>{playbackMessage}</p>}
            {surfaceState === "DISCONNECTED" && playback?.control_url ? (
              <button className="live-recovery-button" type="button" onClick={() => void runControl("recover")}>
                重新连接
              </button>
            ) : null}
            </div>
          )}
        </section>

        <aside className="live-room-rail" aria-label="直播间信息">
          <div className="live-room-host">
            <span className="live-room-avatar" aria-hidden="true">小</span>
            <div>
              <strong>{record.speaker}</strong>
              <span>家庭沟通专家</span>
            </div>
            <span className="live-room-on-air">{sessionLabel}</span>
          </div>
          <div className="live-room-topic">
            <span>{isLiveSession ? "正在讲" : "本场主题"}</span>
            <strong>先听懂，再回应</strong>
            <p>把冲突拆成一个今天就能练习的小动作。</p>
          </div>
          <div className="live-room-chat" aria-label="Sandbox 直播讨论预览">
            <div className="live-room-chat-heading">
              <strong>直播讨论</strong>
              <span>{realtimeState === "live" ? "实时" : "演示"}</span>
            </div>
            <p><b>主持人</b> 欢迎来到小橘灯直播间</p>
            <p><b>小橘灯老师</b> 今天只练习一个方法</p>
            {questions.map((question) => (
              <p key={question.question_ref} className={`live-question-${question.status.toLowerCase()}`}>
                <b>{question.status === "APPROVED" ? "家长提问" : "我的提问"}</b> {question.text}
                {question.status === "PENDING" ? <em>等待人工审核</em> : null}
              </p>
            ))}
          </div>
          {interactionBaseUrl ? (
            <form className="live-room-composer" aria-label="提交直播问题" onSubmit={submitQuestion}>
              <input
                aria-label="向专家提问"
                maxLength={240}
                placeholder="向专家提问，审核后展示"
                value={questionText}
                onChange={(event) => setQuestionText(event.target.value)}
              />
              <button type="submit" disabled={questionText.trim().length < 2 || questionState === "sending"}>
                {questionState === "sending" ? "提交中" : "提交"}
              </button>
            </form>
          ) : (
            <div className="live-room-composer" aria-label="互动能力状态">
              <span>互动服务暂不可用</span>
              <button type="button" disabled>提交</button>
            </div>
          )}
          {questionState === "sent" ? <p className="live-question-feedback" role="status">问题已提交，等待人工审核</p> : null}
          {questionState === "error" ? <p className="live-question-feedback" role="alert">问题暂未送达，请稍后再试</p> : null}
          <a className="live-support-entry" href="#live-service">
            <strong>支持专家与后续服务</strong>
            <span>成人主动进入 · 不影响观看和提问</span>
          </a>
          {incidentBaseUrl ? (
            <button
              className="live-report-entry"
              type="button"
              disabled={incidentState === "sending" || incidentState === "reported"}
              onClick={() => void reportIncident()}
            >
              {incidentState === "reported" ? "已提交人工安全审核" : "举报本场直播"}
            </button>
          ) : null}
          {incidentState === "error" ? <p className="live-question-feedback" role="alert">举报未送达，请稍后重试</p> : null}
        </aside>
      </div>

      <div className="live-detail-content">
        <section className="live-value-panel" aria-labelledby="live-value-heading">
          <p className="live-kicker">本场你会带走什么</p>
          <h4 id="live-value-heading">一个可以马上练习的沟通方法</h4>
          <p>{record.expert_summary}</p>
          <div className="live-problem-tags" aria-label="本场主题">
            {record.problem_tags.map((tag) => <span key={tag}>#{tag}</span>)}
          </div>
        </section>
        <aside className="live-session-card" aria-label="直播时间与参与范围">
          <strong>{record.starts_at}</strong>
          <span>预计至 {record.ends_at}</span>
          <span>仅对{record.applicable_scope}开放</span>
          <span className="live-approved-line">✓ 内容已审核</span>
        </aside>
      </div>

      <section className="live-registration-panel" aria-labelledby="live-registration-heading">
        <div>
          <span className="live-registration-fixture">SANDBOX · SYNTHETIC</span>
          <h4 id="live-registration-heading">预约这场专家直播</h4>
          <p>仅限成人主动操作；服务端负责核验家庭范围与 canonical Consent，页面不会代替授权。</p>
          <ul aria-label="预约提醒说明">
            <li>开播前一天：准备主题与参与时间</li>
            <li>开播前一小时：再次确认是否参加</li>
            <li>直播开始时：提示进入已授权直播间</li>
          </ul>
          <small>当前只展示提醒计划，不会真实发送通知。</small>
        </div>
        <div className="live-registration-actions">
          {registrationState === "confirmed" ? (
            <>
              <strong role="status">已预约本场</strong>
              <button
                type="button"
                className="live-registration-cancel"
                onClick={() => void cancelRegistration()}
              >
                取消预约
              </button>
            </>
          ) : (
            <button
              type="button"
              className="live-registration-submit"
              disabled={
                !registrationEligible ||
                registrationState === "missing" ||
                registrationState === "registering" ||
                registrationState === "cancelling" ||
                registrationState === "cancelled"
              }
              onClick={() => void registerForSession()}
            >
              {registrationState === "registering" ? "预约中…" : "预约本场"}
            </button>
          )}
          {registrationState === "missing" ? (
            <span className="live-registration-message" role="status">预约服务未连接</span>
          ) : null}
          {!registrationEligible ? (
            <span className="live-registration-message" role="status">
              {getRegistrationUnavailableMessage(record)}
            </span>
          ) : null}
          {registrationState === "cancelled" ? (
            <span className="live-registration-message" role="status">预约已取消，不会生成后续提醒。</span>
          ) : null}
          {registrationState === "error" ? (
            <span className="live-registration-message" role="alert">预约状态未确认，请稍后重试。</span>
          ) : null}
        </div>
      </section>

      <p className="live-capability-note">收藏与回看将在获得明确授权后开放。</p>
      {showAdultNextStep ? (
        <section className="live-service-next-step" aria-labelledby="live-service-next-step-heading">
          <span className="live-adult-only">仅限成人</span>
          <div>
            <p className="live-kicker">直播后的下一步</p>
            <h4 id="live-service-next-step-heading">需要继续支持？先了解专家服务方式</h4>
            <p>由家长自主决定，不影响当前直播与家庭内容。</p>
          </div>
          <a className="live-service-button" href="#live-service">查看服务方案</a>
        </section>
      ) : null}
      {showAdultNextStep && replayBaseUrl ? (
        <section className="live-replay-panel" aria-labelledby="live-replay-heading">
          <div>
            <p className="live-kicker">直播回看</p>
            <h4 id="live-replay-heading">错过的部分，现在接着看</h4>
            <p>回看使用独立成人权益；不解锁也不会影响直播观看、提问或安全求助。</p>
          </div>
          {replayState === "available" && replayUrl ? (
            <div className="live-replay-player">
              <video
                aria-label="小橘灯合成直播回看"
                controls
                playsInline
                preload="metadata"
                src={replayUrl}
              />
              <button type="button" className="live-replay-delete" onClick={() => void deleteReplay()}>
                删除回看
              </button>
              <button type="button" className="live-replay-delete" onClick={() => void revokeReplayEntitlement()}>
                撤销回看权益
              </button>
            </div>
          ) : null}
          {replayState === "deleted" ? (
            <div className="live-replay-receipt" role="status">
              <strong>回看已删除</strong>
              <p>源视频、转码、字幕、章节、缓存和供应商副本均已进入删除范围。</p>
              <small>{deletedRefs.length} 项血缘已确认；刷新或重启后也不会恢复。</small>
            </div>
          ) : null}
          {replayState === "idle" || replayState === "error" ? (
            <button
              type="button"
              className="live-replay-open"
              disabled={!commerceBaseUrl}
              onClick={() => void unlockReplay()}
            >
              {replayState === "error" ? "重新解锁回看" : "解锁并播放回看（演示）"}
            </button>
          ) : null}
          {replayState === "unlocked" ? (
            <button type="button" className="live-replay-open" onClick={() => void loadReplay(mediaEntitlementRef)}>
              播放已解锁回看
            </button>
          ) : null}
          {replayState === "revoked" ? (
            <div className="live-replay-receipt" role="status">
              <strong>回看权益已撤销</strong>
              <p>旧播放地址已经失效；服务重启后也不会恢复。</p>
            </div>
          ) : null}
          {replayState === "restoring" ? <p role="status">正在恢复回看权益状态…</p> : null}
          {replayState === "unlocking" ? <p role="status">正在解锁回看…</p> : null}
          {replayState === "loading" ? <p role="status">正在获取回看…</p> : null}
          {replayState === "revoking" ? <p role="status">正在撤销回看权益…</p> : null}
          {replayState === "deleting" ? <p role="status">正在删除全部回看副本…</p> : null}
        </section>
      ) : null}
      {showAdultNextStep ? (
        <LiveReplayKnowledge
          baseUrl={replayKnowledgeBaseUrl}
          replayRef={record.session_ref}
          replayDeleted={replayState === "deleted"}
        />
      ) : null}
      {playback?.control_url && record.fixture_only ? (
        <details className="live-sandbox-controls">
          <summary>连接演练工具</summary>
          <div aria-label="Sandbox 媒体故障演练">
            <button type="button" onClick={() => void runControl("disconnect")}>中断连接</button>
            <button type="button" onClick={() => void runControl("stop")}>结束本场</button>
            <button type="button" onClick={() => void runControl("revoke")}>撤回观看权限</button>
          </div>
        </details>
      ) : null}
      {record.fixture_only ? (
        <details className="live-diagnostics">
          <summary>开发诊断信息</summary>
          <span className="visually-hidden" aria-hidden="true">{SANDBOX_DIAGNOSTIC_MARKERS}</span>
          <dl className="live-detail-grid">
            <div><dt>approval</dt><dd>{record.approval_status}</dd></div>
            <div><dt>expiry</dt><dd>{record.expiry_state}</dd></div>
            <div><dt>audience</dt><dd>{record.audience_scope}</dd></div>
            <div><dt>review ref</dt><dd>{record.review_ref}</dd></div>
            <div><dt>version</dt><dd>{record.version}</dd></div>
            <div><dt>visibility</dt><dd>{record.family_visibility}</dd></div>
            <div><dt>as of</dt><dd>{record.as_of}</dd></div>
            <div><dt>source</dt><dd>{record.source} · FIXTURE_ONLY</dd></div>
          </dl>
        </details>
      ) : null}
    </article>
  );

  async function runControl(action: "disconnect" | "recover" | "stop" | "revoke") {
    if (!playback?.control_url || !isLocalPlaybackUrl(playback.control_url)) {
      setSurfaceState("FAILED");
      return;
    }
    try {
      const response = await fetch(`${playback.control_url}/${action}`, { method: "POST" });
      if (!response.ok) throw new Error("control failed");
      const result = (await response.json()) as { state: MediaPlaybackState; playback_url?: string };
      if (result.playback_url) setMediaUrl(result.playback_url);
      setSurfaceState(result.state);
    } catch {
      setSurfaceState("FAILED");
    }
  }

  async function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = questionText.trim();
    if (!interactionBaseUrl || text.length < 2) return;
    const reference = `question.${Date.now()}`;
    setQuestionState("sending");
    try {
      const response = await fetch(
        `${interactionBaseUrl}/sandbox/live/sessions/${record.session_ref}/questions`,
        {
          method: "POST",
          headers: SYNTHETIC_ACTOR_HEADERS,
          body: JSON.stringify({ question_ref: reference, idempotency_key: reference, text }),
        },
      );
      if (!response.ok) throw new Error("question submit failed");
      const submitted = (await response.json()) as LiveQuestion;
      if (submitted.fixture_only !== true || submitted.source !== "SANDBOX_SYNTHETIC") {
        throw new Error("question source rejected");
      }
      setQuestions((current) => [...current.filter((item) => item.question_ref !== reference), submitted]);
      setQuestionText("");
      setQuestionState("sent");
    } catch {
      setQuestionState("error");
    }
  }

  async function reportIncident() {
    if (!incidentBaseUrl || !isLocalPlaybackUrl(incidentBaseUrl)) return;
    const reference = `incident.synthetic.ui.${Date.now()}`;
    setIncidentState("sending");
    try {
      const response = await fetch(
        `${incidentBaseUrl}/sandbox/live-incidents/sessions/${record.session_ref}/reports`,
        {
          method: "POST",
          headers: SYNTHETIC_ACTOR_HEADERS,
          body: JSON.stringify({
            report_ref: reference,
            idempotency_key: reference,
            reason: "成人请求人工核对本场直播内容",
          }),
        },
      );
      if (!response.ok) throw new Error("incident report failed");
      const result = await response.json() as Record<string, unknown>;
      if (
        result.state !== "PENDING" ||
        result.source !== "SANDBOX_SYNTHETIC" ||
        result.fixture_only !== true ||
        result.external_effect !== false
      ) throw new Error("unsafe incident receipt");
      setIncidentState("reported");
    } catch {
      setIncidentState("error");
    }
  }

  async function registerForSession() {
    if (!registrationApiBaseUrl || !registrationEligible) return;
    const commandRef = `registration.ui.${Date.now()}`;
    setRegistrationState("registering");
    try {
      const receipt = await requestRegistration(
        `${registrationApiBaseUrl}/sandbox/live-control/sessions/${encodeURIComponent(record.session_ref)}/registrations`,
        {
          method: "POST",
          headers: SYNTHETIC_ACTOR_HEADERS,
          body: JSON.stringify({
            idempotency_key: commandRef,
            correlation_id: commandRef,
          }),
        },
      );
      assertRegistrationReceipt(receipt, record.session_ref, "CONFIRMED");
      setRegistrationRef(receipt.registration.registration_ref);
      setRegistrationState("confirmed");
    } catch {
      setRegistrationState("error");
    }
  }

  async function cancelRegistration() {
    if (!registrationApiBaseUrl || !registrationRef) return;
    const commandRef = `registration-cancel.ui.${Date.now()}`;
    setRegistrationState("cancelling");
    try {
      const receipt = await requestRegistration(
        `${registrationApiBaseUrl}/sandbox/live-control/registrations/${encodeURIComponent(registrationRef)}/cancel`,
        {
          method: "POST",
          headers: SYNTHETIC_ACTOR_HEADERS,
          body: JSON.stringify({
            idempotency_key: commandRef,
            correlation_id: commandRef,
          }),
        },
      );
      assertRegistrationReceipt(receipt, record.session_ref, "CANCELLED", registrationRef);
      setRegistrationState("cancelled");
    } catch {
      setRegistrationState("error");
    }
  }

  async function unlockReplay() {
    if (
      !commerceBaseUrl ||
      !replayBaseUrl ||
      !isLocalPlaybackUrl(commerceBaseUrl) ||
      !isLocalPlaybackUrl(replayBaseUrl)
    ) {
      setReplayState("error");
      return;
    }
    const purchaseRef = `media-entitlement.ui.${Date.now()}`;
    const idempotencyKey = `media-entitlement-idempotency.ui.${Date.now()}`;
    setReplayState("unlocking");
    try {
      const purchase = await requestCommerce<MediaPurchase>(
        `${commerceBaseUrl}/sandbox/live-commerce/purchases`,
        {
          method: "POST",
          headers: SYNTHETIC_ACTOR_HEADERS,
          body: JSON.stringify({
            purchase_ref: purchaseRef,
            track: "MEDIA_ENTITLEMENT",
            subject_ref: "replay:media.synthetic.1",
            amount: 1200,
            currency: "CNY_CENT",
            idempotency_key: idempotencyKey,
          }),
        },
      );
      if (purchase.purchase_ref !== purchaseRef || purchase.track !== "MEDIA_ENTITLEMENT") {
        throw new Error("media entitlement receipt mismatch");
      }
      const balance = await loadMediaBalance(commerceBaseUrl, purchaseRef);
      if (balance.entitlement !== "ACTIVE") throw new Error("media entitlement inactive");
      localStorage.setItem(MEDIA_ENTITLEMENT_REF_KEY, purchaseRef);
      setMediaEntitlementRef(purchaseRef);
      await loadReplay(purchaseRef);
    } catch {
      setReplayState("error");
    }
  }

  async function loadReplay(entitlementRef: string) {
    if (!replayBaseUrl || !entitlementRef || !isLocalPlaybackUrl(replayBaseUrl)) {
      setReplayState("error");
      return;
    }
    setReplayState("loading");
    try {
      const response = await fetch(`${replayBaseUrl}/sandbox/replays/media.synthetic.1`, {
        cache: "no-store",
        headers: { ...SYNTHETIC_ACTOR_HEADERS, "X-Media-Entitlement-Ref": entitlementRef },
      });
      if (!response.ok) throw new Error("replay read failed");
      const replay = (await response.json()) as ReplayView;
      if (replay.source !== "SANDBOX_SYNTHETIC" || replay.fixture_only !== true) {
        throw new Error("replay source rejected");
      }
      if (replay.state === "DELETED") {
        setReplayUrl("");
        setReplayState("deleted");
        return;
      }
      if (!replay.playback_url || !isLocalPlaybackUrl(replay.playback_url)) {
        throw new Error("replay capability rejected");
      }
      setReplayUrl(replay.playback_url);
      setReplayState("available");
    } catch {
      setReplayState("error");
    }
  }

  async function revokeReplayEntitlement() {
    if (!commerceBaseUrl || !mediaEntitlementRef || !isLocalPlaybackUrl(commerceBaseUrl)) {
      setReplayState("error");
      return;
    }
    const reversalRef = `media-entitlement-reversal.ui.${Date.now()}`;
    setReplayState("revoking");
    try {
      await requestCommerce(
        `${commerceBaseUrl}/sandbox/live-commerce/purchases/${encodeURIComponent(mediaEntitlementRef)}/reversals`,
        {
          method: "POST",
          headers: SYNTHETIC_ACTOR_HEADERS,
          body: JSON.stringify({
            reversal_ref: reversalRef,
            idempotency_key: reversalRef,
            reason: "adult withdrew synthetic replay entitlement",
          }),
        },
      );
      const balance = await loadMediaBalance(commerceBaseUrl, mediaEntitlementRef);
      if (balance.entitlement !== "REVOKED") throw new Error("media entitlement still active");
      setReplayUrl("");
      setReplayState("revoked");
    } catch {
      setReplayState("error");
    }
  }

  async function deleteReplay() {
    if (!replayBaseUrl || !isLocalPlaybackUrl(replayBaseUrl)) {
      setReplayState("error");
      return;
    }
    setReplayState("deleting");
    const reference = `replay-deletion.${Date.now()}`;
    try {
      const response = await fetch(`${replayBaseUrl}/sandbox/replays/media.synthetic.1/delete`, {
        method: "POST",
        headers: SYNTHETIC_ACTOR_HEADERS,
        body: JSON.stringify({
          deletion_ref: reference,
          idempotency_key: reference,
          reason: "adult requested sandbox replay deletion",
        }),
      });
      if (!response.ok) throw new Error("replay deletion failed");
      const receipt = (await response.json()) as DeletionView;
      if (receipt.source !== "SANDBOX_SYNTHETIC" || receipt.fixture_only !== true) {
        throw new Error("deletion receipt rejected");
      }
      setReplayUrl("");
      setDeletedRefs(receipt.affected_refs);
      setReplayState("deleted");
    } catch {
      setReplayState("error");
    }
  }

}

async function loadMediaBalance(
  commerceBaseUrl: string,
  purchaseRef: string,
  signal?: AbortSignal,
): Promise<MediaBalance> {
  return await requestCommerce<MediaBalance>(
    `${commerceBaseUrl}/sandbox/live-commerce/purchases/${encodeURIComponent(purchaseRef)}/balances`,
    { headers: SYNTHETIC_ACTOR_HEADERS, signal },
  );
}

async function requestCommerce<T extends CommerceEvidence>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) throw new Error(`commerce request failed: ${response.status}`);
  const result = (await response.json()) as T;
  if (result.source !== "SANDBOX_SYNTHETIC" || result.fixture_only !== true || result.external_effect !== false) {
    throw new Error("commerce evidence rejected");
  }
  return result;
}

function resolveRegistrationBaseUrl(explicitBaseUrl?: string): string | undefined {
  if (explicitBaseUrl !== undefined) {
    return isLocalPlaybackUrl(explicitBaseUrl) ? explicitBaseUrl.replace(/\/$/, "") : undefined;
  }
  return resolveLiveControlBaseUrl(import.meta.env);
}

async function requestRegistration(url: string, init: RequestInit): Promise<RegistrationReceipt> {
  const response = await fetch(url, init);
  if (!response.ok) throw new Error(`registration request failed: ${response.status}`);
  const payload = (await response.json()) as RegistrationReceipt | DirectRegistrationReceipt;
  const receipt = "registration" in payload
    ? payload
    : {
        registration: payload,
        source: payload.source,
        fixture_only: payload.fixture_only,
        external_effect: payload.external_effect,
      };
  if (
    receipt.source !== "SANDBOX_SYNTHETIC" ||
    receipt.fixture_only !== true ||
    receipt.external_effect !== false
  ) {
    throw new Error("registration evidence rejected");
  }
  return receipt;
}

function assertRegistrationReceipt(
  receipt: RegistrationReceipt,
  sessionRef: string,
  status: RegistrationView["status"],
  registrationRef?: string,
): void {
  const registration = receipt.registration;
  if (
    !registration ||
    !registration.registration_ref ||
    registration.session_ref !== sessionRef ||
    registration.tenant_id !== "tenant.synthetic.alpha" ||
    registration.family_id !== "family.synthetic.alpha" ||
    registration.guardian_id !== "actor.synthetic.adult" ||
    !registration.consent_ref ||
    registration.status !== status ||
    (registrationRef !== undefined && registration.registration_ref !== registrationRef)
  ) {
    throw new Error("registration receipt is outside the synthetic adult scope");
  }
}

function getRegistrationUnavailableMessage(record: LiveRecord): string {
  if (record.status === "WITHDRAWN") return "本场已撤回，不能预约。";
  if (record.status === "EXPIRED" || record.expiry_state === "EXPIRED") {
    return "本场已过期，不能预约。";
  }
  if (record.approval_status !== "APPROVED") return "本场尚未通过审核，不能预约。";
  return "当前场次不满足 Family 预约条件。";
}

function isLocalPlaybackUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return ["localhost", "127.0.0.1"].includes(url.hostname) && ["http:", "https:"].includes(url.protocol);
  } catch {
    return false;
  }
}

function parseRealtimeQuestion(value: unknown): LiveQuestion {
  const record = typeof value === "object" && value !== null
    ? value as Record<string, unknown>
    : null;
  if (
    record === null ||
    typeof record.question_ref !== "string" ||
    typeof record.session_ref !== "string" ||
    typeof record.text !== "string" ||
    !["PENDING", "APPROVED", "REJECTED"].includes(String(record.status)) ||
    record.source !== "SANDBOX_SYNTHETIC" ||
    record.fixture_only !== true
  ) throw new Error("unsafe realtime question");
  return record as LiveQuestion;
}

function getPlaybackMessage(state: SurfaceState): string {
  switch (state) {
    case "WAITING_AUTHORIZATION":
      return "视频服务暂未连接，请稍后刷新或返回直播首页。";
    case "LOADING":
      return "视频正在准备。";
    case "LIVE":
      return "视频已准备好，点击播放开始观看。";
    case "DISCONNECTED":
      return "直播连接中断。";
    case "RESTARTED":
      return "连接已经恢复，可以继续观看。";
    case "ENDED":
      return "本场直播已经结束。";
    case "STOPPED":
      return "本场直播已经停止。";
    case "REVOKED":
      return "观看权限已经撤回。";
    case "FAILED":
      return "视频暂时不可用。";
  }
}

function getPlaybackLabel(state: SurfaceState): string {
  if (state === "LIVE" || state === "RESTARTED") return "可以播放";
  if (state === "LOADING") return "正在准备";
  return "暂不可用";
}

function getRecoveryHint(state: SurfaceState): string {
  if (state === "DISCONNECTED") return "检查网络后重新连接，不会自动切换视频来源。";
  if (state === "REVOKED") return "本页不会继续加载视频。";
  if (state === "STOPPED" || state === "ENDED") return "感谢观看，回看开放后会在这里显示。";
  return "请稍后再试。";
}

function getSessionLabel(status: LiveRecord["status"]): string {
  if (status === "LIVE") return "直播中";
  if (status === "SCHEDULED") return "即将开始";
  if (status === "WITHDRAWN") return "已撤下";
  return "已结束";
}

function getEffectiveSessionLabel(
  status: LiveRecord["status"],
  playbackState: SurfaceState,
): string {
  if (playbackState === "STOPPED" || playbackState === "ENDED") return "已结束";
  if (playbackState === "REVOKED") return "已停止";
  return getSessionLabel(status);
}
