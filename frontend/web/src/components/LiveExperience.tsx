import { useState } from "react";
import { LiveDiscoveryCard } from "./LiveDiscoveryCard";
import { LiveDetailPage } from "./LiveDetailPage";
import {
  LIVE_STATE_COPY,
  resolveLiveView,
  type LiveEnvironment,
  type LiveViewModel,
} from "../live/liveCatalog";

type Props = {
  environment?: LiveEnvironment;
  viewModel?: LiveViewModel;
};

export function LiveExperience({ environment = import.meta.env, viewModel }: Props) {
  const [showDetail, setShowDetail] = useState(false);
  const model = viewModel ?? resolveLiveView(environment);
  const copy = LIVE_STATE_COPY[model.state];

  return (
    <section className="live-shell" aria-labelledby="live-discovery-heading">
      <div className="live-shell-heading">
        <div>
          <p className="live-kicker">小橘灯 · 家庭可见</p>
          <h2 id="live-discovery-heading">发现专家直播</h2>
        </div>
        <span className="live-scope-badge">family-private</span>
      </div>
      {model.state === "success" && model.record ? (
        showDetail ? (
          <LiveDetailPage record={model.record} onBack={() => setShowDetail(false)} />
        ) : (
          <LiveDiscoveryCard record={model.record} onOpenDetail={() => setShowDetail(true)} />
        )
      ) : (
        <div className={`live-state live-state-${model.state}`} role="status" aria-live="polite">
          <strong>{copy.label}</strong>
          <p>{copy.message}</p>
        </div>
      )}
    </section>
  );
}
