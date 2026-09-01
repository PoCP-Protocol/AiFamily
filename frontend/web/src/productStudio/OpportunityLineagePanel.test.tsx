import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { OpportunityLineage } from "./decisionApi";
import { OpportunityLineagePanel } from "./OpportunityLineagePanel";

const complete: OpportunityLineage = {
  market_signal: { id: "signal:one", status: "ACTIVE", version: 1, raw_text: "家长反复提到催促冲突", source_ref: "research:one", evidence_refs: ["evidence:signal"] },
  customer_insight: { id: "insight:one", status: "ACTIVE", version: 1, statement: "家庭需要降低催促频率", signal_id: "signal:one", evidence_refs: ["evidence:insight"], ai_provenance: null },
  opportunity: { id: "opportunity:one", status: "INVEST", version: 2, statement: "设计逐步交还责任的服务", insight_id: "insight:one", evidence_refs: ["evidence:opportunity"], ai_provenance: null },
  growth_problem: { id: "problem:one", status: "ACTIVE", version: 1, symptom: "高频冲突", opportunity_id: "opportunity:one", evidence_refs: [] },
  growth_strategy: { id: "strategy:one", status: "DRAFT", version: 1, statement: "共同规划", problem_id: "problem:one" },
  completeness: "STRUCTURALLY_COMPLETE_TO_OPPORTUNITY",
  review_state: "NEEDS_HUMAN_DECISION",
  reason_codes: ["AUTHORITATIVE_HUMAN_DECISION_NOT_IN_CONTRACT", "PRODUCT_PACKAGE_BACKLINK_NOT_IN_CONTRACT"],
};

describe("OpportunityLineagePanel", () => {
  it("separates facts, inference, recommendation gap, and human decision gap", () => {
    render(<OpportunityLineagePanel conceptTitle="21 天责任转移营" lineage={complete} />);
    const details = screen.getByText(/查看 21 天责任转移营/).closest("details")!;
    expect(details).toHaveTextContent("FACT · 来源记录");
    expect(details).toHaveTextContent("INFERENCE · 机会内容");
    expect(details).toHaveTextContent("RECOMMENDATION · 当前合同缺失");
    expect(details).toHaveTextContent("HUMAN_DECISION · 待治理");
    expect(details).toHaveTextContent("遗留领域状态：INVEST；它不是已证明的人工决定");
    expect(within(details).queryByText(/机会总分|家庭评分|排名|赢家/)).not.toBeInTheDocument();
  });

  it("shows an incomplete upstream tail without inventing an opportunity", () => {
    render(<OpportunityLineagePanel conceptTitle="待研究候选" lineage={{ ...complete, market_signal: null, customer_insight: null, opportunity: null, completeness: "INCOMPLETE_UPSTREAM" }} />);
    expect(screen.getByText(/尚无 Opportunity，不以默认 WATCH 代替/)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("INCOMPLETE_UPSTREAM");
  });
});
