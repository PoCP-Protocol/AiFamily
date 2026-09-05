import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  ProductStudioApiError,
  type ProductStudioApiClient,
  type ProductDraftResponse,
} from "./api";
import { ProductFactoryComposer } from "./ProductFactoryComposer";

const draft: ProductDraftResponse = {
  status: "DRAFT",
  provenance_ref: "model-draft:demand-001",
  demand_id: "demand-001",
};

const draftWithCompilerReport: ProductDraftResponse = {
  ...draft,
  compiler_report: { passed: false, checks: {} },
};

const fillForm = async () => {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("需求陈述"), "家庭需要更容易开始的小行动。");
  await user.type(screen.getByLabelText("场景"), "evening_routine");
  await user.type(screen.getByLabelText(/来源引用/), "voc:001");
  await user.type(screen.getByLabelText("目标分群"), "家庭照护者");
  await user.type(screen.getByLabelText("假设（逗号或换行分隔）"), "家长愿意尝试");
  await user.type(screen.getByLabelText("未知项（逗号或换行分隔）"), "持续性未知");
  await user.type(screen.getByLabelText("下一步验证"), "访谈并观察七天");
  await user.type(screen.getByLabelText("provenance_ref"), "model-draft:demand-001");
  return user;
};

const clientWith = (result: ProductDraftResponse | Error): ProductStudioApiClient => ({
  createDemandFrame: vi.fn(async () => {
    if (result instanceof Error) throw result;
    return result;
  }),
  createMarketInsight: vi.fn(),
  createCompetitorEvidence: vi.fn(),
});

describe("ProductFactoryComposer", () => {
  it("renders all demand draft fields and a DRAFT-only disclaimer", () => {
    render(<ProductFactoryComposer client={clientWith(draft)} />);
    expect(screen.getByLabelText("需求陈述")).toBeInTheDocument();
    expect(screen.getByLabelText("下一步验证")).toBeInTheDocument();
    expect(screen.getByText(/不是家庭事实/)).toBeInTheDocument();
  });

  it("submits the typed demand frame and displays only DRAFT provenance", async () => {
    const client = clientWith(draft);
    render(<ProductFactoryComposer client={client} />);
    const user = await fillForm();
    await user.click(screen.getByRole("button", { name: "提交需求草案" }));
    expect(await screen.findByText("DRAFT")).toBeInTheDocument();
    expect(screen.getByText(/model-draft:demand-001/)).toBeInTheDocument();
    expect(client.createDemandFrame).toHaveBeenCalledWith(expect.objectContaining({ evidence_refs: ["voc:001"], assumptions: ["家长愿意尝试"] }), expect.any(String));
    expect(screen.getByText(/不能作为已验证市场事实/)).toBeInTheDocument();
  });

  it("renders the server compiler report without inventing a local result", async () => {
    const client = clientWith(draftWithCompilerReport);
    render(<ProductFactoryComposer client={client} />);
    await fillForm();
    await userEvent.setup().click(screen.getByRole("button", { name: "提交需求草案" }));
    expect(await screen.findByRole("region", { name: "Product Compiler Report" })).toBeInTheDocument();
    expect(screen.getByText("不可进入 Human Gate")).toBeInTheDocument();
  });

  it("shows INVALID_INPUT without calling the client for incomplete form", async () => {
    const client = clientWith(draft);
    render(<ProductFactoryComposer client={client} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "提交需求草案" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("INVALID_INPUT");
    expect(client.createDemandFrame).not.toHaveBeenCalled();
  });

  it.each(["assumptions", "unknowns"] as const)("fails fast when %s has no entries", async (field) => {
    const client = clientWith(draft);
    render(<ProductFactoryComposer client={client} />);
    await fillForm();
    fireEvent.change(screen.getByLabelText(field === "assumptions" ? "假设（逗号或换行分隔）" : "未知项（逗号或换行分隔）"), { target: { value: "" } });
    await userEvent.setup().click(screen.getByRole("button", { name: "提交需求草案" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("INVALID_INPUT");
    expect(client.createDemandFrame).not.toHaveBeenCalled();
  });

  it("renders a 422 ProductStudioApiError code", async () => {
    const client = clientWith(new ProductStudioApiError("INVALID_INPUT", "evidence_refs_invalid", 422));
    render(<ProductFactoryComposer client={client} />);
    await fillForm();
    await userEvent.setup().click(screen.getByRole("button", { name: "提交需求草案" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("INVALID_INPUT");
  });

  it("renders a network TIMEOUT error", async () => {
    const client = clientWith(new ProductStudioApiError("TIMEOUT", "网络不可达"));
    render(<ProductFactoryComposer client={client} />);
    await fillForm();
    await userEvent.setup().click(screen.getByRole("button", { name: "提交需求草案" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("TIMEOUT");
  });

  it("fails closed when the HTTP response has no provenance", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ status: "DRAFT" }), { status: 201 }));
    const { HttpProductStudioApiClient } = await import("./api");
    render(<ProductFactoryComposer client={new HttpProductStudioApiClient({ fetchImpl })} />);
    await fillForm();
    await userEvent.setup().click(screen.getByRole("button", { name: "提交需求草案" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("INVALID_RESPONSE");
  });

  it("reuses the same idempotency key after a retry", async () => {
    const keys: string[] = [];
    let attempts = 0;
    const client = clientWith(draft);
    client.createDemandFrame = vi.fn(async (_input, key) => {
      keys.push(key);
      if (attempts++ === 0) throw new ProductStudioApiError("CONFLICT", "冲突");
      return draft;
    });
    render(<ProductFactoryComposer client={client} />);
    const user = await fillForm();
    await user.click(screen.getByRole("button", { name: "提交需求草案" }));
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "提交需求草案" }));
    expect(await screen.findByText("DRAFT")).toBeInTheDocument();
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });

  it("maps datetime-local expiry to a timezone-aware request", async () => {
    const client = clientWith(draft);
    render(<ProductFactoryComposer client={client} />);
    await fillForm();
    fireEvent.change(screen.getByLabelText("草案有效期"), { target: { value: "2099-02-03T04:05" } });
    await userEvent.setup().click(screen.getByRole("button", { name: "提交需求草案" }));
    expect(client.createDemandFrame).toHaveBeenCalledWith(expect.objectContaining({ expires_at: "2099-02-03T04:05:00+08:00" }), expect.any(String));
  });
});
