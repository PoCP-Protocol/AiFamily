import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { WebRoot } from "../main";

const originalPath = window.location.pathname;

afterEach(() => window.history.replaceState({}, "", originalPath));

describe("Web Product Studio route", () => {
  it("enters the staged Product Studio workspace on Demand", async () => {
    window.history.replaceState({}, "", "/product-studio");
    render(<WebRoot />);
    expect(screen.getByRole("heading", { name: "服务产品 AI 研发工作台" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Demand/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "创建需求草案" })).toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("tab", { name: /Market Evidence/ }));
    expect(screen.getByRole("heading", { name: "市场与竞品证据工作台" })).toBeInTheDocument();
    expect(screen.getByText(/新证据固定以 UNKNOWN 创建/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("tab", { name: /Concept Decision/ }));
    expect(screen.getByRole("heading", { name: "产品概念候选决策台" })).toBeInTheDocument();
    expect(screen.getByText(/不会排序或自动选择赢家/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("tab", { name: /Package Review/ }));
    expect(screen.getByRole("heading", { name: "产品包证据准入与评审" })).toBeInTheDocument();
    expect(screen.getByText(/浏览器只提交设计意图和 receipt locator/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("tab", { name: /Portfolio & Catalog/ }));
    expect(screen.getByRole("heading", { name: "证据到选定产品包对照工作台" })).toBeInTheDocument();
    expect(screen.getByText(/不计算综合分，不做家庭评分或排名/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("tab", { name: /Sandbox/ }));
    expect(screen.getByRole("heading", { name: "产品设计工厂" })).toBeInTheDocument();
    expect(screen.getByTestId("product-studio-environment")).toHaveTextContent("Sandbox");
    expect(screen.getByText(/所有 AI 内容均为 DRAFT/)).toBeInTheDocument();
  });

  it("keeps the root path on Experience Studio", () => {
    window.history.replaceState({}, "", "/");
    render(<WebRoot />);
    expect(screen.getByRole("heading", { name: "先被理解，再一起决定。" })).toBeInTheDocument();
  });

  it("can walk the fixture through Gate to PLM with an explicit human GO", async () => {
    window.history.replaceState({}, "", "/product-studio");
    const user = userEvent.setup();
    render(<WebRoot />);
    await user.click(screen.getByRole("tab", { name: /Sandbox/ }));
    const advance = screen.getByRole("button", { name: "推进到下一阶段" });
    await user.click(advance);
    await user.click(advance);
    await user.click(advance);
    expect(screen.getByRole("status")).toHaveTextContent("IPD Gate");
    expect(advance).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "GO" }));
    await user.click(advance);
    expect(screen.getByRole("status")).toHaveTextContent("PLM");
  });
});
