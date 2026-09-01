import { FormEvent, useEffect, useRef, useState } from "react";
import type { LiveRecord, MediaPlaybackState } from "../live/liveCatalog";

type Props = {
  record: LiveRecord;
  interactionBaseUrl?: string;
  replayBaseUrl?: string;
  commerceBaseUrl?: string;
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
type ReplayState = "idle" | "loading" | "available" | "deleting" | "deleted" | "error";

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

type CommerceReceipt = {
  status: "SANDBOX_AUTHORIZED";
  gross_amount: number;
  allocations: { beneficiary_ref: string; amount: number }[];
  external_effect: false;
  source: "SANDBOX_SYNTHETIC";
  fixture_only: true;
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

export function LiveDetailPage({
  record,
  interactionBaseUrl,
  replayBaseUrl,
  commerceBaseUrl,
  onBack,
}: Props) {
  const playback = record.playback;
  const [surfaceState, setSurfaceState] = useState<SurfaceState>(
    playback?.state ?? "WAITING_AUTHORIZATION",
  );
  const [mediaUrl, setMediaUrl] = useState(playback ? playback.playback_url : "");
  const [showServiceDetails, setShowServiceDetails] = useState(false);
  const [questions, setQuestions] = useState<LiveQuestion[]>([]);
  const [questionText, setQuestionText] = useState("");
  const [questionState, setQuestionState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [replayState, setReplayState] = useState<ReplayState>("idle");
  const [replayUrl, setReplayUrl] = useState("");
  const [deletedRefs, setDeletedRefs] = useState<string[]>([]);
  const [membership, setMembership] = useState<string | null>(null);
  const [supportState, setSupportState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [supportReceipt, setSupportReceipt] = useState<CommerceReceipt | null>(null);
  const hasStartedPlayback = useRef(false);
  const canRenderVideo =
    playback?.source === "synthetic" &&
    playback.fixture_only &&
    ["LIVE", "LOADING", "RESTARTED"].includes(surfaceState) &&
    isLocalPlaybackUrl(mediaUrl);
  const playbackMessage = getPlaybackMessage(surfaceState);
  const showAdultNextStep = ["ENDED", "STOPPED", "REVOKED"].includes(surfaceState);

  useEffect(() => {
    if (!interactionBaseUrl) return;
    const controller = new AbortController();
    void fetch(`${interactionBaseUrl}/sandbox/live/sessions/media.synthetic.1/questions`, {
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
  }, [interactionBaseUrl]);

  useEffect(() => {
    if (!commerceBaseUrl) return;
    const controller = new AbortController();
    void fetch(`${commerceBaseUrl}/sandbox/live-commerce/membership`, {
      cache: "no-store",
      headers: SYNTHETIC_ACTOR_HEADERS,
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error("membership read failed");
        return response.json() as Promise<{
          membership: string | null;
          source: "SANDBOX_SYNTHETIC";
          fixture_only: true;
        }>;
      })
      .then((value) => {
        if (value.source === "SANDBOX_SYNTHETIC" && value.fixture_only === true) {
          setMembership(value.membership);
        }
      })
      .catch(() => undefined);
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
        <span className="live-status-badge">{getSessionLabel(record.status)}</span>
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
            <span className="live-room-on-air">直播中</span>
          </div>
          <div className="live-room-topic">
            <span>正在讲</span>
            <strong>先听懂，再回应</strong>
            <p>把冲突拆成一个今天就能练习的小动作。</p>
          </div>
          <div className="live-room-chat" aria-label="Sandbox 直播讨论预览">
            <div className="live-room-chat-heading">
              <strong>直播讨论</strong>
              <span>演示</span>
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
          {commerceBaseUrl ? (
            <section className="live-room-support" aria-label="成人支持专家">
              <div>
                <strong>支持本场专家</strong>
                <span>{membership ? "橘灯会员 · 成人专属" : "仅限成人 · Sandbox"}</span>
              </div>
              <div className="live-room-support-actions">
                <button type="button" onClick={() => void supportExpert("TIP", 500, "CNY_CENT")}>
                  打赏 5 元
                </button>
                <button type="button" onClick={() => void supportExpert("POINTS", 100, "POINT")}>
                  送 100 积分
                </button>
              </div>
              {supportState === "sending" ? <small role="status">正在校验成人权限与账本…</small> : null}
              {supportState === "sent" && supportReceipt ? (
                <small role="status">
                  演示支持已记录；专家分配 {supportReceipt.allocations[0]?.amount ?? 0}
                  {supportReceipt.gross_amount === 500 ? " 分" : " 积分"}，未发生真实扣款。
                </small>
              ) : null}
              {supportState === "error" ? <small role="alert">支持服务不可用，未产生扣款。</small> : null}
            </section>
          ) : null}
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

      <p className="live-capability-note">收藏与回看将在获得明确授权后开放。</p>
      {showAdultNextStep ? (
        <section className="live-service-next-step" aria-labelledby="live-service-next-step-heading">
          <span className="live-adult-only">仅限成人</span>
          <div>
            <p className="live-kicker">直播后的下一步</p>
            <h4 id="live-service-next-step-heading">需要继续支持？先了解专家服务方式</h4>
            <p>由家长自主决定，不影响当前直播与家庭内容。</p>
          </div>
          <button
            className="live-service-button"
            type="button"
            aria-expanded={showServiceDetails}
            onClick={() => setShowServiceDetails((visible) => !visible)}
          >
            {showServiceDetails ? "收起说明" : "了解服务方式"}
          </button>
          {showServiceDetails ? (
            <p className="live-service-detail" role="status">
              当前仅展示服务说明，不会自动下单、扣费或联系专家。
            </p>
          ) : null}
        </section>
      ) : null}
      {showAdultNextStep && replayBaseUrl ? (
        <section className="live-replay-panel" aria-labelledby="live-replay-heading">
          <div>
            <p className="live-kicker">直播回看</p>
            <h4 id="live-replay-heading">错过的部分，现在接着看</h4>
            <p>回看仅对当前合成家庭开放；删除后旧播放链接立即失效。</p>
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
            </div>
          ) : null}
          {replayState === "deleted" ? (
            <div className="live-replay-receipt" role="status">
              <strong>回看已删除</strong>
              <p>源视频、转码、字幕、章节、缓存和供应商副本均已进入删除范围。</p>
              <small>{deletedRefs.length} 项血缘已确认；刷新或重启后也不会恢复。</small>
            </div>
          ) : null}
          {["idle", "error"].includes(replayState) ? (
            <button type="button" className="live-replay-open" onClick={() => void loadReplay()}>
              {replayState === "error" ? "重新获取回看" : "播放回看"}
            </button>
          ) : null}
          {replayState === "loading" ? <p role="status">正在获取回看…</p> : null}
          {replayState === "deleting" ? <p role="status">正在删除全部回看副本…</p> : null}
        </section>
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
        `${interactionBaseUrl}/sandbox/live/sessions/media.synthetic.1/questions`,
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

  async function loadReplay() {
    if (!replayBaseUrl || !isLocalPlaybackUrl(replayBaseUrl)) {
      setReplayState("error");
      return;
    }
    setReplayState("loading");
    try {
      const response = await fetch(`${replayBaseUrl}/sandbox/replays/media.synthetic.1`, {
        cache: "no-store",
        headers: SYNTHETIC_ACTOR_HEADERS,
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

  async function supportExpert(kind: "TIP" | "POINTS", amount: number, currency: "CNY_CENT" | "POINT") {
    if (!commerceBaseUrl || !isLocalPlaybackUrl(commerceBaseUrl)) {
      setSupportState("error");
      return;
    }
    const reference = `support.${kind.toLowerCase()}.${Date.now()}`;
    setSupportState("sending");
    try {
      const response = await fetch(
        `${commerceBaseUrl}/sandbox/live-commerce/sessions/media.synthetic.1/support`,
        {
          method: "POST",
          headers: SYNTHETIC_ACTOR_HEADERS,
          body: JSON.stringify({
            intent_ref: reference,
            idempotency_key: reference,
            kind,
            amount,
            currency,
          }),
        },
      );
      if (!response.ok) throw new Error("support rejected");
      const receipt = (await response.json()) as CommerceReceipt;
      if (
        receipt.source !== "SANDBOX_SYNTHETIC" ||
        receipt.fixture_only !== true ||
        receipt.external_effect !== false
      ) {
        throw new Error("support receipt rejected");
      }
      setSupportReceipt(receipt);
      setSupportState("sent");
    } catch {
      setSupportReceipt(null);
      setSupportState("error");
    }
  }
}

function isLocalPlaybackUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return ["localhost", "127.0.0.1"].includes(url.hostname) && ["http:", "https:"].includes(url.protocol);
  } catch {
    return false;
  }
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
