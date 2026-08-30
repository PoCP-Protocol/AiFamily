import { useReducer } from "react";
import { canAdvance, PRODUCT_STAGE_ORDER, productStudioReducer } from "./state";
import type {
  EvidenceRef,
  GateDecision,
  LifecycleRecommendation,
  ProductStage,
  ProductStudioState,
} from "./types";

type ProductStudioProps = {
  initialState: ProductStudioState;
  onStateChange?: (state: ProductStudioState) => void;
  environmentLabel?: string;
};

const stageLabels: Record<ProductStage, string> = {
  DEMAND: "Demand",
  MARKET_EVIDENCE: "Market / Competitor Evidence",
  PRODUCT_PACKAGE: "ProductPackage",
  GATE: "IPD Gate",
  PLM: "PLM",
  STOPPED: "Stopped · KILL",
};

const gateLabels: Record<GateDecision, string> = {
  GO: "GO",
  NO_GO: "NO-GO",
  CONDITIONAL: "CONDITIONAL",
};

const lifecycleLabels: Record<LifecycleRecommendation, string> = {
  SCALE: "SCALE",
  REVISE: "REVISE",
  KILL: "KILL",
};

function EvidenceRefs({ refs }: { refs: EvidenceRef[] }) {
  if (refs.length === 0) return <p className="muted">暂无证据引用，不能推进 Gate。</p>;
  return (
    <ul aria-label="证据引用">
      {refs.map((evidence) => (
        <li key={evidence.ref}>
          <code>{evidence.ref}</code> {evidence.label} · {evidence.status}
        </li>
      ))}
    </ul>
  );
}

export function ProductStudio({ initialState, onStateChange, environmentLabel = "Sandbox Fixture" }: ProductStudioProps) {
  const [state, dispatch] = useReducer(productStudioReducer, initialState);
  const act = (action: Parameters<typeof dispatch>[0]) => {
    // Keep the component pure from API/AI concerns; the parent owns persistence.
    const next = productStudioReducer(state, action);
    if (next !== state) onStateChange?.(next);
    dispatch(action);
  };

  return (
    <section aria-label="Product Studio" className="product-studio">
      <header>
        <p className="eyebrow">IPD · PDM · PLM</p>
        <h1>产品设计工厂</h1>
        <p data-testid="product-studio-environment">{environmentLabel} · 不连接真实模型或生产数据</p>
        <p className="muted">所有 AI 内容均为 DRAFT；证据、Gate 和生命周期决定必须可追溯并由人批准。</p>
      </header>

      <nav aria-label="产品开发阶段" className="product-stage-rail">
        {PRODUCT_STAGE_ORDER.map((stage, index) => {
          const active = state.currentStage === stage;
          const reached = state.currentStage === "STOPPED"
            ? stage === "DEMAND" || stage === "MARKET_EVIDENCE" || stage === "PRODUCT_PACKAGE" || stage === "GATE"
            : PRODUCT_STAGE_ORDER.indexOf(state.currentStage) >= index;
          return (
            <span key={stage} aria-current={active ? "step" : undefined} data-reached={reached}>
              {index + 1}. {stageLabels[stage]}
            </span>
          );
        })}
      </nav>

      <div className="product-studio-grid">
        <article className="panel" data-stage="DEMAND">
          <h2>Demand</h2>
          <h3>{state.demand.title}</h3>
          <p>{state.demand.summary}</p>
          <span className="draft-badge">DRAFT</span>
          <EvidenceRefs refs={state.demand.evidenceRefs} />
        </article>

        <article className="panel" data-stage="MARKET_EVIDENCE">
          <h2>Market / Competitor Evidence</h2>
          <h3>{state.market.title}</h3>
          <p>{state.market.summary}</p>
          <span className="draft-badge">DRAFT</span>
          <h4>市场证据</h4>
          <EvidenceRefs refs={state.market.evidenceRefs} />
          <h4>竞品证据</h4>
          <EvidenceRefs refs={state.market.competitorEvidence} />
        </article>

        <article className="panel" data-stage="PRODUCT_PACKAGE">
          <h2>ProductPackage</h2>
          <h3>{state.productPackage.title}</h3>
          <p>{state.productPackage.summary}</p>
          <p>产品形态：{state.productPackage.durationDays} 天 · 主导产品区：{state.productPackage.zone}</p>
          <span className="draft-badge">DRAFT</span>
          <EvidenceRefs refs={state.productPackage.evidenceRefs} />
        </article>

        <article className="panel" data-stage="GATE">
          <h2>IPD Gate</h2>
          <p>Gate 决定不是 AI 自动发布；没有证据引用时不能推进。</p>
          <div role="group" aria-label="Gate 决定">
            {(Object.keys(gateLabels) as GateDecision[]).map((decision) => (
              <button
                key={decision}
                type="button"
                aria-pressed={state.gate.decision === decision}
                disabled={state.currentStage !== "GATE"}
                onClick={() => act({ type: "SET_GATE_DECISION", decision })}
              >
                {gateLabels[decision]}
              </button>
            ))}
          </div>
          <p>当前决定：{state.gate.decision ?? "待人工决定"}</p>
          {state.currentStage === "STOPPED" ? <p role="alert">NO_GO：停止进入正常 PLM，生命周期建议为 KILL。</p> : null}
          <EvidenceRefs refs={state.gate.evidenceRefs} />
        </article>

        <article className="panel" data-stage="PLM">
          <h2>PLM Lifecycle</h2>
          <p>试点反馈只产生生命周期建议，不直接写入家庭成长事实。</p>
          <div role="group" aria-label="生命周期建议">
            {(Object.keys(lifecycleLabels) as LifecycleRecommendation[]).map((recommendation) => (
              <button
                key={recommendation}
                type="button"
                aria-pressed={state.plm.recommendation === recommendation}
                disabled={state.currentStage !== "PLM"}
                onClick={() => act({ type: "SET_LIFECYCLE_RECOMMENDATION", recommendation })}
              >
                {lifecycleLabels[recommendation]}
              </button>
            ))}
          </div>
          <p>当前建议：{state.plm.recommendation ?? "待试点证据"}</p>
          <EvidenceRefs refs={state.plm.evidenceRefs} />
        </article>
      </div>

      <footer>
        <button type="button" onClick={() => act({ type: "ADVANCE_STAGE" })} disabled={!canAdvance(state)}>
          推进到下一阶段
        </button>
        <span role="status">当前阶段：{stageLabels[state.currentStage]}</span>
      </footer>
    </section>
  );
}

export type { ProductStudioProps };
