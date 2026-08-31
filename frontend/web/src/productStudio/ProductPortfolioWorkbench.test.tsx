import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ProductStudioApiError } from "./api";
import { ProductPortfolioWorkbench } from "./ProductPortfolioWorkbench";
import type { ProductPackageReviewApiClient } from "./productPackageReviewApi";
import { sampleProductPackageReviewResponse } from "./productPackageReviewFixtures";
import { sampleCatalogSnapshot, secondProductPackageReviewResponse } from "./productPortfolioFixtures";

function client(): ProductPackageReviewApiClient {
  return {
    submit: vi.fn(),
    get: vi.fn(async (draftId) => draftId === secondProductPackageReviewResponse.draft.draft_id
      ? secondProductPackageReviewResponse
      : sampleProductPackageReviewResponse),
  };
}

describe("ProductPortfolioWorkbench", () => {
  it("keeps the production workspace fail-closed while runtime contracts are missing", async () => {
    const api = client();
    render(<ProductPortfolioWorkbench client={api} contractPreview />);

    expect(screen.getByText("合同预览，尚未接入生产 Opportunity/Portfolio/Catalog 运行时")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "加载选定集合" })).toBeDisabled();
    expect(screen.getByText("尚未加载可信 ProductPackage 选定集合。")).toBeInTheDocument();
    expect(api.get).not.toHaveBeenCalled();
  });

  it("loads immutable packages in input order and shows discrete evidence and reuse", async () => {
    const api = client();
    render(<ProductPortfolioWorkbench client={api} catalog={sampleCatalogSnapshot} />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/DRAFT ID/), "product-package-draft:one\nproduct-package-draft:two");
    await user.click(screen.getByRole("button", { name: "加载选定集合" }));

    const snapshot = await screen.findByRole("region", { name: "ProductPackage DRAFT 选定集合" });
    expect(snapshot).toHaveTextContent("2 个冻结版本");
    expect(snapshot).toHaveTextContent("UNIQUE1");
    expect(snapshot).toHaveTextContent("ADVANTAGE1");
    expect(snapshot).toHaveTextContent("MARKET_EXISTENCE · ADMITTED");
    expect(screen.getAllByText("component:action:v1").length).toBeGreaterThan(1);
    expect(snapshot).toHaveTextContent("2 个 DRAFT");
    expect(vi.mocked(api.get).mock.calls.map(([id]) => id)).toEqual([
      "product-package-draft:one",
      "product-package-draft:two",
    ]);
    expect(screen.queryByRole("button", { name: /按.*分数.*排序/ })).not.toBeInTheDocument();
  });

  it("refreshes against prior content hashes and preserves the old snapshot on failure", async () => {
    const api = client();
    vi.mocked(api.get).mockRejectedValueOnce(new ProductStudioApiError("INVALID_RESPONSE", "内容哈希漂移"));
    render(<ProductPortfolioWorkbench client={api} initialPackages={[sampleProductPackageReviewResponse]} />);

    await userEvent.setup().click(screen.getByRole("button", { name: "按内容哈希刷新快照" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("内容哈希漂移");
    expect(screen.getByRole("region", { name: "ProductPackage DRAFT 选定集合" })).toHaveTextContent("product-package-draft:one");
    expect(screen.getByRole("status")).toHaveTextContent("HISTORICAL_SNAPSHOT");
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      "product-package-draft:one",
      sampleProductPackageReviewResponse.draft.content_hash,
    ));
  });

  it("rejects duplicate identifiers before any network call", async () => {
    const api = client();
    render(<ProductPortfolioWorkbench client={api} />);
    await userEvent.setup().type(screen.getByLabelText(/DRAFT ID/), "draft:one\ndraft:one");
    await userEvent.setup().click(screen.getByRole("button", { name: "加载选定集合" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("不能重复");
    expect(api.get).not.toHaveBeenCalled();
  });
});
