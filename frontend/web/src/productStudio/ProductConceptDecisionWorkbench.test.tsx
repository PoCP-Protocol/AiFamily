import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  DecisionApiError,
  ZONE_DIMENSIONS,
  type ProductConceptCandidate,
  type ProductDecisionApiClient,
} from "./decisionApi";
import { ProductConceptDecisionWorkbench } from "./ProductConceptDecisionWorkbench";

const candidate = (
  id: string,
  title: string,
  recommended: "COMMODITY" | "ADVANTAGE" | "UNIQUE",
  approved: "COMMODITY" | "ADVANTAGE" | "UNIQUE" | null = null,
  status: "SCORED" | "UNDER_REVIEW" | "APPROVED" | "REJECTED" | "RETIRED" = "SCORED",
): ProductConceptCandidate => ({
  concept: { id, version: 1, strategy_id: "strategy:001", title, description: `${title} 描述`, status: "DRAFT" },
  lineage: {
    market_signal: { id: `signal:${id}`, status: "ACTIVE", version: 1, raw_text: `${title} 市场信号`, source_ref: "research:interview", evidence_refs: [`evidence:${id}:signal`] },
    customer_insight: { id: `insight:${id}`, status: "ACTIVE", version: 1, statement: `${title} 客户洞察`, signal_id: `signal:${id}`, evidence_refs: [`evidence:${id}:insight`], ai_provenance: null },
    opportunity: { id: "opportunity:decision-room", status: "WATCH", version: 1, statement: `${title} 机会推断`, insight_id: `insight:${id}`, evidence_refs: [`evidence:${id}:opportunity`], ai_provenance: null },
    growth_problem: { id: `problem:${id}`, status: "ACTIVE", version: 1, symptom: `${title} 成长问题`, opportunity_id: "opportunity:decision-room", evidence_refs: [`evidence:${id}:problem`] },
    growth_strategy: { id: "strategy:001", status: "DRAFT", version: 1, statement: `${title} 策略草案`, problem_id: `problem:${id}` },
    completeness: "STRUCTURALLY_COMPLETE_TO_OPPORTUNITY",
    review_state: "NEEDS_HUMAN_DECISION",
    reason_codes: ["AUTHORITATIVE_HUMAN_DECISION_NOT_IN_CONTRACT", "PRODUCT_PACKAGE_BACKLINK_NOT_IN_CONTRACT"],
  },
  assessment: {
    id: `assessment:${id}`,
    version: 1,
    subject_type: "PRODUCT_CONCEPT",
    subject_ref: id,
    zone_policy_version_id: "zone-policy:v1",
    status,
    recommended_zone: recommended,
    approved_zone: approved,
    override_reason: approved && approved !== recommended ? "人工判断证据尚不足以支持规则推荐" : null,
    reviewed_by: approved ? "human:reviewer" : null,
    reviewed_at: approved ? "2026-09-01T00:00:00Z" : null,
    review_reason: approved ? "完成跨职能证据评审" : null,
    differentiation_index: 60,
    defensibility_index: 55,
    dimension_assessments: ZONE_DIMENSIONS.map((dimension, index) => ({
      dimension,
      score: 50 + index,
      rationale: `${title} 的 ${dimension} 依据`,
      evidence_refs: [`evidence:${id}:${dimension}`],
      evidence_strength: 0.7,
    })),
  },
});

const candidates = [
  candidate("concept:first", "先输入的候选", "COMMODITY"),
  candidate("concept:second", "后输入的候选", "UNIQUE", "ADVANTAGE", "APPROVED"),
];

const clientWith = (result: ProductConceptCandidate[] | Error = candidates): ProductDecisionApiClient => ({
  loadCandidates: vi.fn(async () => {
    if (result instanceof Error) throw result;
    return result;
  }),
});

function fillReferences(): void {
  fireEvent.change(screen.getByLabelText("候选 1 concept_id"), { target: { value: "concept:first" } });
  fireEvent.change(screen.getByLabelText("候选 1 assessment_id"), { target: { value: "assessment:concept:first" } });
  fireEvent.change(screen.getByLabelText("候选 2 concept_id"), { target: { value: "concept:second" } });
  fireEvent.change(screen.getByLabelText("候选 2 assessment_id"), { target: { value: "assessment:concept:second" } });
}

async function loadCandidates(client = clientWith()): Promise<ProductDecisionApiClient> {
  render(<ProductConceptDecisionWorkbench client={client} />);
  fillReferences();
  await userEvent.setup().click(screen.getByRole("button", { name: "读取候选与三区证据" }));
  await screen.findByLabelText("产品概念候选列表");
  return client;
}

describe("ProductConceptDecisionWorkbench", () => {
  it("keeps the production workspace fail-closed while chain routes are unmounted", () => {
    const client = clientWith();
    render(<ProductConceptDecisionWorkbench client={client} contractPreview />);
    expect(screen.getByText("合同预览，Concept chain 与三区路由尚未生产挂载")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "读取候选与三区证据" })).toBeDisabled();
    expect(client.loadCandidates).not.toHaveBeenCalled();
  });

  it("manages 2–5 candidate references", async () => {
    render(<ProductConceptDecisionWorkbench client={clientWith()} />);
    expect(screen.getAllByLabelText(/候选 \d concept_id/)).toHaveLength(2);
    const add = screen.getByRole("button", { name: "增加候选" });
    await userEvent.setup().click(add);
    await userEvent.setup().click(add);
    await userEvent.setup().click(add);
    expect(screen.getAllByLabelText(/候选 \d concept_id/)).toHaveLength(5);
    expect(add).toBeDisabled();
    await userEvent.setup().click(screen.getByRole("button", { name: "移除候选 3" }));
    expect(screen.getAllByLabelText(/候选 \d concept_id/)).toHaveLength(4);
  });

  it("preserves server input order and separates recommendation from approval", async () => {
    await loadCandidates();
    const cards = screen.getAllByRole("article");
    expect(cards.map((card) => within(card).getByRole("heading", { level: 3 }).textContent)).toEqual(["先输入的候选", "后输入的候选"]);
    expect(cards[0]).toHaveAttribute("data-candidate-order", "1");
    expect(cards[0]).toHaveTextContent("同质区");
    expect(cards[0]).toHaveTextContent("待人工治理");
    expect(cards[1]).toHaveTextContent("独特区");
    expect(cards[1]).toHaveTextContent("优势区");
    expect(cards[1]).toHaveTextContent("zone-policy:v1");
    expect(cards[1]).toHaveTextContent("完成跨职能证据评审");
    expect(cards[1]).toHaveTextContent("覆盖原因");
    expect(screen.getByText(/不会排序或自动选择赢家/)).toBeInTheDocument();
    expect(screen.getAllByRole("radio").every((radio) => !(radio as HTMLInputElement).checked)).toBe(true);
  });

  it("requires an explicit candidate, reason, preparation, and confirmation for selection", async () => {
    const onDecisionDraft = vi.fn();
    const client = clientWith();
    render(<ProductConceptDecisionWorkbench client={client} onDecisionDraft={onDecisionDraft} />);
    fillReferences();
    await userEvent.setup().click(screen.getByRole("button", { name: "读取候选与三区证据" }));
    await screen.findByLabelText("产品概念候选列表");

    const prepare = screen.getByRole("button", { name: "准备提议选择候选" });
    expect(prepare).toBeDisabled();
    await userEvent.setup().click(screen.getByRole("radio", { name: "人工选择候选 2" }));
    fireEvent.change(screen.getByLabelText("人工决策理由"), { target: { value: "更符合当前证据，但仍需 Gate。" } });
    expect(prepare).toBeEnabled();
    await userEvent.setup().click(prepare);
    expect(screen.getByText(/不会调用 approve\/reject/)).toBeInTheDocument();
    expect(onDecisionDraft).not.toHaveBeenCalled();
    await userEvent.setup().click(screen.getByRole("button", { name: "确认生成提议选择草案" }));

    const output = screen.getByLabelText("候选决策草案");
    expect(output).toHaveTextContent("DRAFT · PROPOSE_CANDIDATE_SELECTION");
    expect(output).toHaveTextContent("未持久化");
    expect(onDecisionDraft).toHaveBeenCalledWith(expect.objectContaining({
      status: "DRAFT",
      action: "PROPOSE_CANDIDATE_SELECTION",
      concept_id: "concept:second",
      concept_version: 1,
      opportunity_id: "opportunity:decision-room",
      assessment_version: 1,
      zone_policy_version_id: "zone-policy:v1",
      persisted: false,
    }));
  });

  it("creates only a local RETURN_TO_RESEARCH draft and never invokes another API method", async () => {
    const client = await loadCandidates();
    await userEvent.setup().click(screen.getByRole("radio", { name: "人工选择候选 1" }));
    fireEvent.change(screen.getByLabelText("人工决策理由"), { target: { value: "需要补充真实家庭访谈证据。" } });
    await userEvent.setup().click(screen.getByRole("button", { name: "准备退回研究" }));
    await userEvent.setup().click(screen.getByRole("button", { name: "确认生成退回研究草案" }));
    expect(screen.getByLabelText("候选决策草案")).toHaveTextContent("DRAFT · RETURN_TO_RESEARCH");
    expect(screen.getByLabelText("候选决策草案")).toHaveTextContent("WEB_DERIVED_FROM_CHAIN · UNKNOWN_NOT_IN_CONTRACT");
    expect(client.loadCandidates).toHaveBeenCalledTimes(1);
    expect(Object.keys(client)).toEqual(["loadCandidates"]);
  });

  it("brings an evidence gap into research without inventing a reason or draft", async () => {
    const onDecisionDraft = vi.fn();
    const client = clientWith();
    render(<ProductConceptDecisionWorkbench client={client} onDecisionDraft={onDecisionDraft} />);
    fillReferences();
    await userEvent.setup().click(screen.getByRole("button", { name: "读取候选与三区证据" }));
    await screen.findByLabelText("产品概念候选列表");

    await userEvent.setup().click(screen.getByRole("button", { name: /带入退回研究：先输入的候选/ }));

    expect(screen.getByRole("radio", { name: "人工选择候选 1" })).toBeChecked();
    expect(screen.getByLabelText("人工决策理由")).toHaveFocus();
    expect(screen.getByLabelText("人工决策理由")).toHaveValue("");
    expect(screen.getByLabelText("带入的研究缺口")).toHaveTextContent("UNKNOWN_NOT_IN_CONTRACT");
    expect(screen.queryByLabelText("候选决策草案")).not.toBeInTheDocument();
    expect(onDecisionDraft).not.toHaveBeenCalled();
    expect(client.loadCandidates).toHaveBeenCalledTimes(1);
  });

  it("focuses an existing research reason without clearing same-candidate work", async () => {
    await loadCandidates();
    await userEvent.setup().click(screen.getByRole("radio", { name: "人工选择候选 1" }));
    fireEvent.change(screen.getByLabelText("人工决策理由"), { target: { value: "仍需补访谈样本" } });
    await userEvent.setup().click(screen.getByRole("button", { name: "准备退回研究" }));
    await userEvent.setup().click(screen.getByRole("button", { name: "确认生成退回研究草案" }));
    await userEvent.setup().click(screen.getByRole("button", { name: /带入退回研究：先输入的候选/ }));
    expect(screen.getByLabelText("人工决策理由")).toHaveValue("仍需补访谈样本");
    expect(screen.getByLabelText("人工决策理由")).toHaveFocus();
    expect(screen.getByLabelText("候选决策草案")).toHaveTextContent("DRAFT · RETURN_TO_RESEARCH");
  });

  it("does not silently discard a draft when a radio switches candidates", async () => {
    await loadCandidates();
    await userEvent.setup().click(screen.getByRole("radio", { name: "人工选择候选 1" }));
    fireEvent.change(screen.getByLabelText("人工决策理由"), { target: { value: "保留当前研究草案" } });
    await userEvent.setup().click(screen.getByRole("button", { name: "准备退回研究" }));
    await userEvent.setup().click(screen.getByRole("button", { name: "确认生成退回研究草案" }));

    await userEvent.setup().click(screen.getByRole("radio", { name: "人工选择候选 2" }));

    expect(screen.getByRole("radio", { name: "人工选择候选 1" })).toBeChecked();
    expect(screen.getByLabelText("人工决策理由")).toHaveValue("保留当前研究草案");
    expect(screen.getByLabelText("候选决策草案")).toBeInTheDocument();
    expect(screen.getByText(/请先完成当前流程，再切换候选/)).toBeInTheDocument();
  });

  it("returns an incomplete lineage to research without dereferencing a missing Opportunity", async () => {
    const incomplete = candidates.map((item) => ({
      ...item,
      lineage: {
        ...item.lineage,
        market_signal: null,
        customer_insight: null,
        opportunity: null,
        growth_problem: { ...item.lineage.growth_problem, opportunity_id: null },
        completeness: "INCOMPLETE_UPSTREAM" as const,
      },
    }));
    const onDecisionDraft = vi.fn();
    render(<ProductConceptDecisionWorkbench client={clientWith(incomplete)} onDecisionDraft={onDecisionDraft} />);
    fillReferences();
    await userEvent.setup().click(screen.getByRole("button", { name: "读取候选与三区证据" }));
    await screen.findByLabelText("产品概念候选列表");
    await userEvent.setup().click(screen.getByRole("radio", { name: "人工选择候选 1" }));
    expect(screen.getByText(/UPSTREAM_OPPORTUNITY_NOT_RETURNED/)).toBeInTheDocument();
    expect(screen.queryByText(/该评估已终止/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("人工决策理由"), { target: { value: "上游机会缺失，退回补证。" } });
    await userEvent.setup().click(screen.getByRole("button", { name: "准备退回研究" }));
    await userEvent.setup().click(screen.getByRole("button", { name: "确认生成退回研究草案" }));
    expect(onDecisionDraft).toHaveBeenCalledWith(expect.objectContaining({ opportunity_id: null, opportunity_version: null }));
  });

  it("prevents selecting a terminal assessment but still allows returning it to research", async () => {
    await loadCandidates(clientWith([
      candidate("concept:first", "终止候选", "COMMODITY", null, "REJECTED"),
      candidates[1],
    ]));
    await userEvent.setup().click(screen.getByRole("radio", { name: "人工选择候选 1" }));
    fireEvent.change(screen.getByLabelText("人工决策理由"), { target: { value: "重新研究" } });
    expect(screen.getByRole("button", { name: "准备提议选择候选" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "准备退回研究" })).toBeEnabled();
    expect(screen.getByText(/ASSESSMENT_OR_CONCEPT_TERMINAL/)).toBeInTheDocument();
  });

  it("shows a stable, understandable API error", async () => {
    render(<ProductConceptDecisionWorkbench client={clientWith(new DecisionApiError("FORBIDDEN", "当前会话无权查看产品候选。", 403))} />);
    fillReferences();
    await userEvent.setup().click(screen.getByRole("button", { name: "读取候选与三区证据" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("FORBIDDEN · 当前会话无权查看产品候选");
    expect(screen.queryByLabelText("产品概念候选列表")).not.toBeInTheDocument();
  });
});
