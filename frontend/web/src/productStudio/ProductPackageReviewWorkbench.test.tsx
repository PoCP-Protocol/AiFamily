import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ProductStudioApiError } from "./api";
import { ProductPackageReviewWorkbench } from "./ProductPackageReviewWorkbench";
import type { ProductPackageReviewApiClient } from "./productPackageReviewApi";
import {
  sampleProductPackageReviewInput,
  sampleProductPackageReviewResponse,
} from "./productPackageReviewFixtures";

function client(): ProductPackageReviewApiClient {
  return {
    submit: vi.fn(async () => sampleProductPackageReviewResponse),
    get: vi.fn(async () => ({ ...sampleProductPackageReviewResponse, replayed: true })),
  };
}

describe("ProductPackageReviewWorkbench", () => {
  it("blocks incomplete intent before calling the API", async () => {
    const api = client();
    render(<ProductPackageReviewWorkbench client={api} />);

    await userEvent.setup().click(screen.getByRole("button", { name: "提交 ProductPackage 人工评审" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("INVALID_INPUT");
    expect(api.submit).not.toHaveBeenCalled();
  });

  it("submits browser intent and explains the server-owned evidence admission", async () => {
    const api = client();
    render(<ProductPackageReviewWorkbench client={api} initialInput={sampleProductPackageReviewInput} />);

    await userEvent.setup().click(screen.getByRole("button", { name: "提交 ProductPackage 人工评审" }));

    const output = await screen.findByRole("status", { name: "ProductPackage 评审提交结果" });
    expect(output).toHaveTextContent("DRAFT · v1.2.0");
    expect(output).toHaveTextContent("已批准三区评估结果");
    expect(output).toHaveTextContent("UNIQUE");
    expect(output).toHaveTextContent("MARKET_EXISTENCE");
    expect(output).toHaveTextContent("role:PARENT_GUARDIAN");
    expect(output).toHaveTextContent("这不是产品批准，也不是家庭成长事实");
    expect(api.submit).toHaveBeenCalledWith(
      sampleProductPackageReviewInput,
      expect.stringMatching(/^product-package-review:/),
    );
    const submitted = vi.mocked(api.submit).mock.calls[0][0] as unknown as Record<string, unknown>;
    expect(submitted).not.toHaveProperty("zone");
    expect(submitted).not.toHaveProperty("claim_type");
    expect(submitted).not.toHaveProperty("source_provenance_ref");

    await userEvent.setup().click(screen.getByRole("button", { name: "提交 ProductPackage 人工评审" }));
    expect(api.submit).toHaveBeenCalledTimes(2);
    expect(vi.mocked(api.submit).mock.calls[1][1]).toBe(vi.mocked(api.submit).mock.calls[0][1]);
  });

  it("retries a timeout with the same idempotency key", async () => {
    const api = client();
    vi.mocked(api.submit)
      .mockRejectedValueOnce(new ProductStudioApiError("TIMEOUT", "暂时超时"))
      .mockResolvedValueOnce(sampleProductPackageReviewResponse);
    render(<ProductPackageReviewWorkbench client={api} initialInput={sampleProductPackageReviewInput} />);

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "提交 ProductPackage 人工评审" }));
    await user.click(await screen.findByRole("button", { name: "使用同一幂等键重试" }));
    await screen.findByRole("status", { name: "ProductPackage 评审提交结果" });

    expect(api.submit).toHaveBeenCalledTimes(2);
    expect(vi.mocked(api.submit).mock.calls[0][1]).toBe(vi.mocked(api.submit).mock.calls[1][1]);
  });

  it("reads the immutable server snapshot without resubmitting", async () => {
    const api = client();
    render(<ProductPackageReviewWorkbench client={api} initialInput={sampleProductPackageReviewInput} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "提交 ProductPackage 人工评审" }));
    await user.click(await screen.findByRole("button", { name: "回读服务端冻结快照" }));

    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      "product-package-draft:one",
      sampleProductPackageReviewResponse.draft.content_hash,
    ));
    expect(api.submit).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("幂等重放")).toBeInTheDocument();
  });
});
