import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { WebRoot } from "../main";

const originalPath = window.location.pathname;

afterEach(() => window.history.replaceState({}, "", originalPath));

describe("Web Product Studio route", () => {
  it("enters the independent Sandbox Product Studio page", () => {
    window.history.replaceState({}, "", "/product-studio");
    render(<WebRoot />);
    expect(screen.getByRole("heading", { name: "产品设计工厂" })).toBeInTheDocument();
    expect(screen.getByTestId("product-studio-environment")).toHaveTextContent("Sandbox");
    expect(screen.getByRole("heading", { name: "创建需求草案" })).toBeInTheDocument();
    expect(screen.getByText(/提交后仅显示 DRAFT 和可追溯 provenance/)).toBeInTheDocument();
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
