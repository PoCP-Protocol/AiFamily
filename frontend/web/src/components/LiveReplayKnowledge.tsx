import { useEffect, useState } from "react";

type Props = {
  baseUrl?: string;
  replayRef: string;
  replayDeleted?: boolean;
};

type Chapter = {
  title: string;
  body: string;
};

type KnowledgeItem = {
  knowledge_ref: string;
  replay_ref: string;
  card_title: string;
  card_body: string;
  chapters: Chapter[];
  state: "APPROVED";
  reviewed_by: string;
  review_reason: string;
  source: "SANDBOX_SYNTHETIC";
  fixture_only: true;
  external_effect: false;
  fact_write: false;
};

type LoadState = "loading" | "ready" | "empty" | "deleted" | "unavailable";

const ACTOR_HEADERS = {
  "Content-Type": "application/json",
  "X-Sandbox-Source": "SANDBOX_SYNTHETIC",
  "X-Fixture-Only": "true",
  "X-Tenant-Id": "tenant.synthetic.alpha",
  "X-Family-Id": "family.synthetic.alpha",
  "X-Actor-Id": "actor.synthetic.adult",
  "X-Actor-Role": "ADULT_VIEWER",
};

export function LiveReplayKnowledge({ baseUrl, replayRef, replayDeleted = false }: Props) {
  const [state, setState] = useState<LoadState>(baseUrl ? "loading" : "unavailable");
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [bookmarked, setBookmarked] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (replayDeleted) {
      setItems([]);
      setBookmarked(new Set());
      setState("deleted");
      return;
    }
    if (!baseUrl || !isLocalSandboxUrl(baseUrl)) {
      setState("unavailable");
      return;
    }
    const controller = new AbortController();
    setState("loading");
    void fetch(`${baseUrl}/sandbox/replay-knowledge/replays/${encodeURIComponent(replayRef)}/knowledge`, {
      cache: "no-store",
      headers: ACTOR_HEADERS,
      signal: controller.signal,
    })
      .then(async (response) => {
        if (response.status === 410) {
          setItems([]);
          setState("deleted");
          return;
        }
        if (!response.ok) throw new Error("knowledge provider rejected");
        const payload = await response.json() as unknown;
        if (!Array.isArray(payload) || !payload.every((item) => isApprovedKnowledge(item, replayRef))) {
          throw new Error("unsafe knowledge shape");
        }
        setItems(payload);
        setState(payload.length > 0 ? "ready" : "empty");
      })
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setItems([]);
          setState("unavailable");
        }
      });
    return () => controller.abort();
  }, [baseUrl, replayDeleted, replayRef]);

  return (
    <section className="live-value-panel" aria-labelledby="replay-knowledge-heading">
      <p className="live-kicker">回放笔记</p>
      <h4 id="replay-knowledge-heading">把一场直播，留下能反复用的方法</h4>
      {state === "loading" ? <p role="status">正在整理人工审核后的章节…</p> : null}
      {state === "empty" ? <p role="status">这场回放还没有通过人工审核的知识卡。</p> : null}
      {state === "deleted" ? (
        <p role="status">回放与衍生章节已删除，刷新或重启后不会恢复。</p>
      ) : null}
      {state === "unavailable" ? (
        <p role="status">回放知识服务暂不可用，页面已安全关闭内容展示。</p>
      ) : null}
      {state === "ready" ? items.map((item) => (
        <article key={item.knowledge_ref} aria-label={`知识卡 ${item.card_title}`}>
          <h5>{item.card_title}</h5>
          <p>{item.card_body}</p>
          <ol>
            {item.chapters.map((chapter) => (
              <li key={`${item.knowledge_ref}-${chapter.title}`}>
                <strong>{chapter.title}</strong>
                <p>{chapter.body}</p>
              </li>
            ))}
          </ol>
          <button
            type="button"
            className="live-replay-open"
            disabled={bookmarked.has(item.knowledge_ref)}
            onClick={() => void bookmark(item)}
          >
            {bookmarked.has(item.knowledge_ref) ? "已收藏到家庭笔记" : "收藏这张知识卡"}
          </button>
          <small>人工审核 · {item.source} · fixture_only</small>
        </article>
      )) : null}
    </section>
  );

  async function bookmark(item: KnowledgeItem) {
    if (!baseUrl || !isLocalSandboxUrl(baseUrl)) {
      setState("unavailable");
      return;
    }
    const bookmarkRef = `bookmark.ui.${item.knowledge_ref}`;
    try {
      const response = await fetch(
        `${baseUrl}/sandbox/replay-knowledge/items/${encodeURIComponent(item.knowledge_ref)}/bookmarks`,
        {
          method: "POST",
          headers: ACTOR_HEADERS,
          body: JSON.stringify({ bookmark_ref: bookmarkRef, idempotency_key: bookmarkRef }),
        },
      );
      if (!response.ok) throw new Error("bookmark rejected");
      const payload = await response.json() as unknown;
      if (!isSafeBookmark(payload, item)) throw new Error("unsafe bookmark shape");
      setBookmarked((current) => new Set(current).add(item.knowledge_ref));
    } catch {
      setState("unavailable");
      setItems([]);
    }
  }
}

function isApprovedKnowledge(value: unknown, replayRef: string): value is KnowledgeItem {
  if (!isObject(value) || containsForbiddenField(value)) return false;
  return (
    value.replay_ref === replayRef &&
    typeof value.knowledge_ref === "string" &&
    typeof value.card_title === "string" &&
    typeof value.card_body === "string" &&
    value.state === "APPROVED" &&
    typeof value.reviewed_by === "string" &&
    typeof value.review_reason === "string" &&
    value.source === "SANDBOX_SYNTHETIC" &&
    value.fixture_only === true &&
    value.external_effect === false &&
    value.fact_write === false &&
    Array.isArray(value.chapters) &&
    value.chapters.length > 0 &&
    value.chapters.every((chapter) => (
      isObject(chapter) && typeof chapter.title === "string" && typeof chapter.body === "string"
    ))
  );
}

function isSafeBookmark(value: unknown, item: KnowledgeItem): boolean {
  return isObject(value) &&
    value.knowledge_ref === item.knowledge_ref &&
    value.replay_ref === item.replay_ref &&
    value.actor_id === "actor.synthetic.adult" &&
    value.source === "SANDBOX_SYNTHETIC" &&
    value.fixture_only === true &&
    value.external_effect === false;
}

function containsForbiddenField(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(containsForbiddenField);
  if (!isObject(value)) return false;
  return Object.entries(value).some(([key, nested]) => (
    /child|score|ranking|diagnosis|room_url|playback_token/i.test(key) || containsForbiddenField(nested)
  ));
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isLocalSandboxUrl(value: string): boolean {
  try {
    return ["localhost", "127.0.0.1"].includes(new URL(value).hostname);
  } catch {
    return false;
  }
}
