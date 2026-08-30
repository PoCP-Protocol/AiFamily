import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ProductStudio } from "./ProductStudio";
import { canAdvance, productStudioReducer } from "./state";
import type { EvidenceRef, ProductStudioState } from "./types";

const evidence = (ref: string, kind: "demand" | "market" | "competitor" | "experiment" | "pilot" = "market") => ({
  ref,
  label: `证据 ${ref}`,
  kind,
  status: "VERIFIED" as const,
});

const initialState: ProductStudioState = {
  currentStage: "DEMAND",
  demand: { id: "demand-1", title: "家庭节奏需求", summary: "可核对的需求草案", evidenceRefs: [evidence("d-1", "demand")], status: "DRAFT" },
  market: { id: "market-1", title: "市场洞察", summary: "市场与替代的草案", evidenceRefs: [evidence("m-1")], competitorEvidence: [evidence("c-1", "competitor")], status: "DRAFT" },
  productPackage: { id: "package-1", title: "21 天成长营", summary: "可试点的产品包草案", evidenceRefs: [evidence("p-1", "experiment")], status: "DRAFT", zone: "ADVANTAGE", durationDays: 21 },
  gate: { decision: null, evidenceRefs: [evidence("g-1", "experiment")] },
  plm: { recommendation: null, evidenceRefs: [evidence("pilot-1", "pilot")] },
};

describe("Product Studio", () => {
  it("renders the IPD to PLM chain and keeps every AI artifact as DRAFT", () => {
    render(<ProductStudio initialState={initialState} />);
    expect(screen.getByRole("heading", { name: "产品设计工厂" })).toBeInTheDocument();
    expect(screen.getAllByText("DRAFT")).toHaveLength(3);
    expect(screen.getByText("市场与替代的草案")).toBeInTheDocument();
    expect(screen.getByText("c-1")).toBeInTheDocument();
  });

  it("requires evidence and a gate decision before advancing", async () => {
    const user = userEvent.setup();
    render(<ProductStudio initialState={{ ...initialState, gate: { decision: null, evidenceRefs: [] } }} />);
    const advance = screen.getByRole("button", { name: "推进到下一阶段" });
    expect(advance).toBeEnabled();
    await user.click(advance);
    expect(screen.getByRole("status")).toHaveTextContent("Market / Competitor Evidence");
    expect(screen.getByRole("button", { name: "GO" })).toBeDisabled();
  });

  it("exposes lifecycle choices without implying automatic release", async () => {
    const user = userEvent.setup();
    render(<ProductStudio initialState={{ ...initialState, currentStage: "PLM" }} />);
    await user.click(screen.getByRole("button", { name: "REVISE" }));
    expect(screen.getByText("当前建议：REVISE")).toBeInTheDocument();
    expect(screen.getByText(/不直接写入家庭成长事实/)).toBeInTheDocument();
  });
});

describe("productStudioReducer", () => {
  it("advances sequentially only when gate evidence and decision exist", () => {
    const atGate = { ...initialState, currentStage: "GATE" as const };
    expect(canAdvance({ ...atGate, gate: { decision: null, evidenceRefs: [] } })).toBe(false);
    const next = productStudioReducer(atGate, { type: "SET_GATE_DECISION", decision: "CONDITIONAL" });
    expect(canAdvance(next)).toBe(true);
    expect(productStudioReducer(next, { type: "ADVANCE_STAGE" }).currentStage).toBe("PLM");
  });

  it.each(["UNKNOWN", "STALE", "CONTRADICTED"] as const)("blocks %s evidence from advancing", (status) => {
    const blockedRef: EvidenceRef = { ...evidence("blocked", "demand"), status };
    const state: ProductStudioState = { ...initialState, demand: { ...initialState.demand, evidenceRefs: [blockedRef] } };
    expect(canAdvance(state)).toBe(false);
    expect(productStudioReducer(state, { type: "ADVANCE_STAGE" })).toBe(state);
  });

  it("moves a NO_GO gate to stopped/KILL and never to normal PLM", () => {
    const atGate = { ...initialState, currentStage: "GATE" as const };
    const stopped = productStudioReducer(atGate, { type: "SET_GATE_DECISION", decision: "NO_GO" });
    expect(stopped.currentStage).toBe("STOPPED");
    expect(canAdvance(stopped)).toBe(false);
    expect(productStudioReducer(stopped, { type: "ADVANCE_STAGE" }).currentStage).toBe("STOPPED");
  });

  it("ignores Gate and PLM actions outside their corresponding stage", () => {
    const atDemand = initialState;
    expect(productStudioReducer(atDemand, { type: "SET_GATE_DECISION", decision: "GO" })).toBe(atDemand);
    expect(productStudioReducer(atDemand, { type: "SET_LIFECYCLE_RECOMMENDATION", recommendation: "SCALE" })).toBe(atDemand);
  });
});
