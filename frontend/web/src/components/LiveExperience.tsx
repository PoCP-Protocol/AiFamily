import { useMemo, useState } from "react";
import { LiveDiscoveryCard } from "./LiveDiscoveryCard";
import { LiveDetailPage } from "./LiveDetailPage";
import {
  LIVE_STATE_COPY,
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
  "live-now": { title: "直播中", subtitle: "当前进行" },
  upcoming: { title: "即将开始", subtitle: "下一场" },
  ended: { title: "已结束 / 回看受限", subtitle: "回看受限" },
};

const SECTION_ORDER: LiveSectionKey[] = ["live-now", "upcoming", "ended"];

const sectionFallback = (record: LiveViewModel["record"]): LiveSections => ({
  "live-now": [],
  upcoming: record ? [record] : [],
  ended: [],
});

export function LiveExperience({ environment = import.meta.env, viewModel }: Props) {
  const [showDetail, setShowDetail] = useState(false);
  const [query, setQuery] = useState("");
  const model = viewModel ?? resolveLiveView(environment);
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
        [record.title, record.speaker, record.expert_summary, record.applicable_scope]
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
            <p className="live-kicker">小橘灯 · 专家直播</p>
            <h2 id="live-discovery-heading">为家庭问题找到合适的专家场次</h2>
          </div>
          <div className="live-hero-badges">
            <span className="live-scope-badge">family-private</span>
            <span className="live-readonly">SANDBOX · DEV_ONLY</span>
          </div>
        </div>
        <label className="live-question-search" htmlFor="live-question-search">
          <span>问题搜索</span>
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
        showDetail ? (
          <LiveDetailPage record={model.record} onBack={() => setShowDetail(false)} />
        ) : (
          <div id="live-status" className="live-sections">
            {query.trim() && SECTION_ORDER.every((key) => filteredSections[key].length === 0) ? (
              <div className="live-empty-search" role="status">
                <strong>没有匹配的直播场次</strong>
                <p>换一个家庭问题关键词，或清空搜索继续浏览。</p>
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
                    <span className="live-section-count">{section.length} 场</span>
                  </div>
                  {section.length > 0 ? (
                    <div className="live-section-grid">
                      {section.map((record) => {
                        const canOpenDetail =
                          record === model.record &&
                          record.approval_status === "APPROVED" &&
                          record.expiry_state === "UNEXPIRED";
                        return (
                          <LiveDiscoveryCard
                            key={`${record.title}-${record.starts_at}`}
                            record={record}
                            onOpenDetail={canOpenDetail ? () => setShowDetail(true) : undefined}
                          />
                        );
                      })}
                    </div>
                  ) : (
                    <p className="live-section-empty">暂无可展示场次。</p>
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
