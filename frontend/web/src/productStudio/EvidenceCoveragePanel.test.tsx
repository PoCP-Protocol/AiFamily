import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { OpportunityLineage } from "./decisionApi";
import { EvidenceCoveragePanel } from "./EvidenceCoveragePanel";

const lineage = {
  market_signal: { evidence_refs: ["evidence:signal"] },
  customer_insight: { evidence_refs: [] },
  opportunity: null,
  completeness: "INCOMPLETE_UPSTREAM",
} as unknown as OpportunityLineage;

describe("EvidenceCoveragePanel", () => {
  it("shows coverage and keeps verification explicitly unknown", () => {
    render(<EvidenceCoveragePanel conceptTitle="候选甲" lineage={lineage} />);
    const panel = screen.getByLabelText("候选甲 证据引用覆盖");
    expect(panel).toHaveTextContent("PRESENT_WITH_REFS");
    expect(panel).toHaveTextContent("PRESENT_WITHOUT_REFS");
    expect(panel).toHaveTextContent("NOT_RETURNED");
    expect(panel).toHaveTextContent("UNKNOWN_NOT_IN_CONTRACT");
    expect(panel).toHaveTextContent("WEB_DERIVED_FROM_CHAIN");
    expect(panel).toHaveTextContent("引用存在不代表真实性、适用性或有效期已验证");
    expect(panel).not.toHaveTextContent(/ADMITTED|VERIFIED|READY|评分|排名/);
  });

  it("only asks the parent to begin a return-to-research flow", async () => {
    const onReturnToResearch = vi.fn();
    render(<EvidenceCoveragePanel conceptTitle="候选甲" lineage={lineage} onReturnToResearch={onReturnToResearch} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "带入退回研究：候选甲" }));
    expect(onReturnToResearch).toHaveBeenCalledOnce();
  });
});
