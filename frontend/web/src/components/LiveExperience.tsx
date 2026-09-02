import { useEffect, useMemo, useState } from "react";
import { LiveDiscoveryCard } from "./LiveDiscoveryCard";
import { LiveDetailPage } from "./LiveDetailPage";
import {
  LIVE_STATE_COPY,
  loadLiveControlView,
  resolveLiveCommerceBaseUrl,
  resolveLiveControlBaseUrl,
  resolveLiveInteractionBaseUrl,
  resolveLiveInteractionWsUrl,
  resolveLiveIncidentBaseUrl,
  resolveLiveReplayBaseUrl,
  resolveLiveView,
  type LiveEnvironment,
  type LiveSectionKey,
  type LiveSections,
  type LiveViewModel,
} from "../live/liveCatalog";

type Props = {
  environment?: LiveEnvironment;
  viewModel?: LiveViewModel;
};

const SECTION_COPY: Record<LiveSectionKey, { title: string; subtitle: string }> = {
  "live-now": { title: "正在直播", subtitle: "现在就能看" },
  upcoming: { title: "直播预告", subtitle: "提前了解主题" },
  ended: { title: "往期直播", subtitle: "回看开放后可观看" },
};

const SECTION_ORDER: LiveSectionKey[] = ["live-now", "upcoming", "ended"];

const sectionFallback = (record: LiveViewModel["record"]): LiveSections => ({
  "live-now": [],
  upcoming: record ? [record] : [],
  ended: [],
});

export function LiveExperience({ environment = import.meta.env, viewModel }: Props) {
  const controlBaseUrl = resolveLiveControlBaseUrl(environment);
  const remoteEnabled = viewModel === undefined && controlBaseUrl !== undefined;
  const [remoteModel, setRemoteModel] = useState<LiveViewModel | null>(null);
  const [selectedRecord, setSelectedRecord] = useState<LiveViewModel["record"]>(null);
  const [query, setQuery] = useState("");
  useEffect(() => {
    if (!remoteEnabled) return;
    const controller = new AbortController();
    setRemoteModel(null);
    void loadLiveControlView(environment, controller.signal)
      .then(setRemoteModel)
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setRemoteModel({ state: "error", record: null });
        }
      });
    return () => controller.abort();
  }, [controlBaseUrl, environment, remoteEnabled]);
  const model = viewModel ?? (
    remoteEnabled
      ? remoteModel ?? { state: "loading", record: null }
      : resolveLiveView(environment)
  );
  const copy = LIVE_STATE_COPY[model.state];
  const sections = useMemo(
    () => model.sections ?? sectionFallback(model.record),
    [model.record, model.sections],
  );
  const filteredSections = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    if (!normalizedQuery) return sections;

    return SECTION_ORDER.reduce<LiveSections>((result, key) => {
      result[key] = sections[key].filter((record) =>
        [record.title, record.speaker, record.expert_summary, record.applicable_scope, ...record.problem_tags]
          .join(" ")
          .toLocaleLowerCase()
          .includes(normalizedQuery),
      );
      return result;
    }, { "live-now": [], upcoming: [], ended: [] });
  }, [query, sections]);

  return (
    <section id="live-home" className="live-shell" aria-labelledby="live-discovery-heading">
      <div className="live-home-hero">
        <div className="live-shell-heading">
          <div>
            <p className="live-kicker">小橘灯直播</p>
            <h2 id="live-discovery-heading">和专家一起，把家庭难题聊明白</h2>
            <p className="live-hero-copy">真实场景、清楚方法、当下就能用。</p>
          </div>
          <div className="live-hero-badges">
            <span className="live-scope-badge">家庭专属</span>
            <span className="live-sandbox-mark" title="当前为合成数据演示，不代表真实直播">演示</span>
          </div>
        </div>
        <label className="live-question-search" htmlFor="live-question-search">
          <span>你想解决什么问题？</span>
          <input
            id="live-question-search"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="例如：家庭沟通"
          />
        </label>
      </div>

      {model.state === "success" && model.record ? (
        selectedRecord ? (
          <LiveDetailPage
            record={selectedRecord}
            interactionBaseUrl={resolveLiveInteractionBaseUrl(environment)}
            interactionWsUrl={resolveLiveInteractionWsUrl(environment)}
            incidentBaseUrl={resolveLiveIncidentBaseUrl(environment)}
            replayBaseUrl={resolveLiveReplayBaseUrl(environment)}
            commerceBaseUrl={resolveLiveCommerceBaseUrl(environment)}
            onBack={() => setSelectedRecord(null)}
          />
        ) : (
          <div id="live-status" className="live-sections">
            {query.trim() && SECTION_ORDER.every((key) => filteredSections[key].length === 0) ? (
              <div className="live-empty-search" role="status">
                <strong>没有匹配的直播</strong>
                <p>换一个关键词，或清空搜索继续看看。</p>
              </div>
            ) : null}
            {SECTION_ORDER.map((key) => {
              const section = filteredSections[key];
              const sectionCopy = SECTION_COPY[key];
              return (
                <section className="live-content-section" key={key} aria-labelledby={`live-${key}-heading`}>
                  <div className="live-section-heading">
                    <div>
                      <h3 id={`live-${key}-heading`}>{sectionCopy.title}</h3>
                      <p>{sectionCopy.subtitle}</p>
                    </div>
                    {section.length > 0 ? <span className="live-section-count">{section.length} 场</span> : null}
                  </div>
                  {section.length > 0 ? (
                    <div className="live-section-grid">
                      {section.map((record) => {
                        const canOpenDetail =
                          record.approval_status === "APPROVED" &&
                          record.expiry_state === "UNEXPIRED";
                        return (
                          <LiveDiscoveryCard
                            key={`${record.title}-${record.starts_at}`}
                            record={record}
                            onOpenDetail={canOpenDetail ? () => setSelectedRecord(record) : undefined}
                          />
                        );
                      })}
                    </div>
                  ) : (
                    <p className="live-section-empty">暂时没有内容</p>
                  )}
                </section>
              );
            })}
          </div>
        )
      ) : (
        <div id="live-status" className={`live-state live-state-${model.state}`} role="status" aria-live="polite">
          <strong>{copy.label}</strong>
          <p>{copy.message}</p>
        </div>
      )}
    </section>
  );
}
