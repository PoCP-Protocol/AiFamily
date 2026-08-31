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
  concept: { id, strategy_id: "strategy:001", title, description: `${title} 描述`, status: "DRAFT" },
  assessment: {
    id: `assessment:${id}`,
    subject_type: "PRODUCT_CONCEPT",
    subject_ref: id,
    zone_policy_version_id: "zone-policy:v1",
    status,
    recommended_zone: recommended,
    approved_zone: approved,
    override_reason: approved && approved !== recommended ? "人工判断证据尚不足以支持规则推荐" : null,
    reviewed_by: approved ? "human:reviewer" : null,
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
    expect(cards.map((card) => within(card).getByRole("heading").textContent)).toEqual(["先输入的候选", "后输入的候选"]);
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

    const prepare = screen.getByRole("button", { name: "准备选择候选" });
    expect(prepare).toBeDisabled();
    await userEvent.setup().click(screen.getByRole("radio", { name: "人工选择候选 2" }));
    fireEvent.change(screen.getByLabelText("人工决策理由"), { target: { value: "更符合当前证据，但仍需 Gate。" } });
    expect(prepare).toBeEnabled();
    await userEvent.setup().click(prepare);
    expect(screen.getByText(/不会调用 approve\/reject/)).toBeInTheDocument();
    expect(onDecisionDraft).not.toHaveBeenCalled();
    await userEvent.setup().click(screen.getByRole("button", { name: "确认生成选择草案" }));

    const output = screen.getByLabelText("候选决策草案");
    expect(output).toHaveTextContent("DRAFT · SELECT_CANDIDATE");
    expect(output).toHaveTextContent("未持久化");
    expect(onDecisionDraft).toHaveBeenCalledWith(expect.objectContaining({
      status: "DRAFT",
      action: "SELECT_CANDIDATE",
      concept_id: "concept:second",
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
    expect(client.loadCandidates).toHaveBeenCalledTimes(1);
    expect(Object.keys(client)).toEqual(["loadCandidates"]);
  });

  it("prevents selecting a terminal assessment but still allows returning it to research", async () => {
    await loadCandidates(clientWith([
      candidate("concept:first", "终止候选", "COMMODITY", null, "REJECTED"),
      candidates[1],
    ]));
    await userEvent.setup().click(screen.getByRole("radio", { name: "人工选择候选 1" }));
    fireEvent.change(screen.getByLabelText("人工决策理由"), { target: { value: "重新研究" } });
    expect(screen.getByRole("button", { name: "准备选择候选" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "准备退回研究" })).toBeEnabled();
    expect(screen.getByRole("status")).toHaveTextContent("仅可退回研究");
  });

  it("shows a stable, understandable API error", async () => {
    render(<ProductConceptDecisionWorkbench client={clientWith(new DecisionApiError("FORBIDDEN", "当前会话无权查看产品候选。", 403))} />);
    fillReferences();
    await userEvent.setup().click(screen.getByRole("button", { name: "读取候选与三区证据" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("FORBIDDEN · 当前会话无权查看产品候选");
    expect(screen.queryByLabelText("产品概念候选列表")).not.toBeInTheDocument();
  });
});
