import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  ProductStudioApiError,
  type CompetitorEvidenceDraftResponse,
  type MarketInsightDraftResponse,
  type ProductStudioApiClient,
} from "./api";
import { MarketEvidenceWorkbench } from "./MarketEvidenceWorkbench";

const evidenceDraft: CompetitorEvidenceDraftResponse = {
  status: "DRAFT",
  provenance_ref: "research:competitor-001",
  evidence_refs: ["https://example.test/source"],
  assumptions: ["页面信息仍然有效"],
  unknowns: ["实际使用效果未知"],
  next_validation: "访谈五位家长",
  expires_at: "2099-01-01T00:00:00+08:00",
  evidence_id: "competitor-evidence:001",
  competitor_ref: "competitor:khanmigo",
  claim: "该产品提供家长可见的学习支持工具。",
  source_refs: ["https://example.test/source"],
  source_type: "official_webpage",
  evidence_status: "UNKNOWN",
  demand_ref: "demand:001",
};

const insightDraft: MarketInsightDraftResponse = {
  status: "DRAFT",
  provenance_ref: "research:insight-001",
  evidence_refs: ["research:market-001", evidenceDraft.evidence_id],
  assumptions: ["透明度影响采用"],
  unknowns: ["支付意愿未知"],
  next_validation: "开展概念测试",
  expires_at: "2099-01-01T00:00:00+08:00",
  insight_id: "market-insight:001",
  demand_ref: "demand:001",
  statement: "家长需要透明、可核查的陪伴工具。",
  source_refs: ["research:market-001"],
  competitor_evidence_refs: [evidenceDraft.evidence_id],
};

const clientWith = (overrides: Partial<ProductStudioApiClient> = {}): ProductStudioApiClient => ({
  createDemandFrame: vi.fn(),
  createCompetitorEvidence: vi.fn(async () => evidenceDraft),
  getCompetitorEvidence: vi.fn(async () => evidenceDraft),
  createMarketInsight: vi.fn(async () => insightDraft),
  createProductPackage: vi.fn(),
  ...overrides,
});

function fillEvidenceForm(): void {
  fireEvent.change(screen.getByLabelText("需求引用"), { target: { value: "demand:001" } });
  fireEvent.change(screen.getByLabelText("竞品引用"), { target: { value: "competitor:khanmigo" } });
  fireEvent.change(screen.getByLabelText("可核查主张"), { target: { value: evidenceDraft.claim } });
  fireEvent.change(screen.getByLabelText(/证据来源/), { target: { value: "https://example.test/source" } });
  fireEvent.change(screen.getByLabelText(/证据假设/), { target: { value: "页面信息仍然有效" } });
  fireEvent.change(screen.getByLabelText(/证据未知项/), { target: { value: "实际使用效果未知" } });
  fireEvent.change(screen.getByLabelText("证据下一步验证"), { target: { value: "访谈五位家长" } });
  fireEvent.change(screen.getByLabelText("证据 provenance_ref"), { target: { value: "research:competitor-001" } });
}

function fillInsightForm(): void {
  fireEvent.change(screen.getByLabelText("市场洞察陈述"), { target: { value: insightDraft.statement } });
  fireEvent.change(screen.getByLabelText(/洞察来源/), { target: { value: "research:market-001" } });
  fireEvent.change(screen.getByLabelText(/洞察假设/), { target: { value: "透明度影响采用" } });
  fireEvent.change(screen.getByLabelText(/洞察未知项/), { target: { value: "支付意愿未知" } });
  fireEvent.change(screen.getByLabelText("洞察下一步验证"), { target: { value: "开展概念测试" } });
  fireEvent.change(screen.getByLabelText("洞察 provenance_ref"), { target: { value: "research:insight-001" } });
}

describe("MarketEvidenceWorkbench", () => {
  it("starts with UNKNOWN evidence policy and keeps market insight locked", () => {
    render(<MarketEvidenceWorkbench client={clientWith()} />);
    expect(screen.getByText(/固定以 UNKNOWN 创建/)).toBeInTheDocument();
    expect(screen.getByRole("group", { name: /市场洞察草案/ })).toBeDisabled();
    expect(screen.queryByText(/评分|排名/)).not.toBeInTheDocument();
  });

  it("fails fast on incomplete evidence without calling the API", async () => {
    const client = clientWith();
    render(<MarketEvidenceWorkbench client={client} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "创建并回读竞品证据" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("INVALID_INPUT");
    expect(client.createCompetitorEvidence).not.toHaveBeenCalled();
  });

  it("creates UNKNOWN evidence, reads it back, and blocks Gate", async () => {
    const client = clientWith();
    render(<MarketEvidenceWorkbench client={client} />);
    fillEvidenceForm();
    await userEvent.setup().click(screen.getByRole("button", { name: "创建并回读竞品证据" }));

    expect(await screen.findByRole("status", { name: "" })).toHaveTextContent("不可进入 Gate");
    expect(client.createCompetitorEvidence).toHaveBeenCalledWith(
      expect.objectContaining({
        demand_ref: "demand:001",
        evidence_status: "UNKNOWN",
        evidence_refs: ["https://example.test/source"],
      }),
      expect.any(String),
    );
    expect(client.getCompetitorEvidence).toHaveBeenCalledWith(evidenceDraft.evidence_id);
    expect(screen.getByLabelText("已回读竞品证据")).toHaveTextContent("DRAFT · UNKNOWN");
    expect(screen.getByLabelText("已回读竞品证据")).toHaveTextContent("访谈五位家长");
    expect(screen.getByLabelText("已回读竞品证据")).toHaveTextContent("2099-01-01");
    expect(screen.getByRole("group", { name: /市场洞察草案/ })).toBeEnabled();
  });

  it("automatically references the persisted evidence in a DRAFT market insight", async () => {
    const client = clientWith();
    render(<MarketEvidenceWorkbench client={client} />);
    fillEvidenceForm();
    await userEvent.setup().click(screen.getByRole("button", { name: "创建并回读竞品证据" }));
    await screen.findByLabelText("已回读竞品证据");
    fillInsightForm();
    await userEvent.setup().click(screen.getByRole("button", { name: "创建市场洞察草案" }));

    await waitFor(() => expect(client.createMarketInsight).toHaveBeenCalledWith(
      expect.objectContaining({
        competitor_evidence_refs: [evidenceDraft.evidence_id],
        evidence_refs: ["research:market-001", evidenceDraft.evidence_id],
      }),
      expect.any(String),
    ));
    const result = await screen.findByLabelText("市场洞察草案结果");
    expect(result).toHaveTextContent("DRAFT");
    expect(result).toHaveTextContent(evidenceDraft.evidence_id);
    expect(within(result).getByRole("status")).toHaveTextContent("不可进入 Gate");
  });

  it("does not unlock insight when the persistence read-back fails", async () => {
    const client = clientWith({
      getCompetitorEvidence: vi.fn(async () => {
        throw new ProductStudioApiError("NOT_FOUND", "证据不存在", 404);
      }),
    });
    render(<MarketEvidenceWorkbench client={client} />);
    fillEvidenceForm();
    await userEvent.setup().click(screen.getByRole("button", { name: "创建并回读竞品证据" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("NOT_FOUND");
    expect(screen.getByRole("group", { name: /市场洞察草案/ })).toBeDisabled();
  });

  it("fails before POST when the client cannot prove persistence by read-back", async () => {
    const client = clientWith({ getCompetitorEvidence: undefined });
    render(<MarketEvidenceWorkbench client={client} />);
    fillEvidenceForm();
    await userEvent.setup().click(screen.getByRole("button", { name: "创建并回读竞品证据" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("UNAVAILABLE");
    expect(client.createCompetitorEvidence).not.toHaveBeenCalled();
  });
});
