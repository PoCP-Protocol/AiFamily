import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ProductStudioWorkspace } from "./ProductStudioWorkspace";

describe("ProductStudioWorkspace", () => {
  it("defaults to Demand and exposes one visible tabpanel", () => {
    render(<ProductStudioWorkspace />);
    expect(screen.getByRole("tab", { name: /Demand/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /Market Evidence/ })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByRole("tabpanel")).toHaveAccessibleName(/Demand/);
    expect(screen.getByRole("heading", { name: "创建需求草案" })).toBeInTheDocument();
    expect(screen.getAllByRole("tabpanel", { hidden: true })).toHaveLength(5);
  });

  it("keeps mounted form state while showing only the active panel", async () => {
    render(<ProductStudioWorkspace />);
    fireEvent.change(screen.getByLabelText("需求陈述"), { target: { value: "保留的需求内容" } });
    await userEvent.setup().click(screen.getByRole("tab", { name: /Market Evidence/ }));
    expect(screen.getByLabelText("需求陈述")).not.toBeVisible();
    fireEvent.change(screen.getByLabelText("需求引用"), { target: { value: "demand:kept" } });

    await userEvent.setup().click(screen.getByRole("tab", { name: /Demand/ }));
    expect(screen.getByLabelText("需求陈述")).toHaveValue("保留的需求内容");
    expect(screen.getByLabelText("需求引用")).not.toBeVisible();
    await userEvent.setup().click(screen.getByRole("tab", { name: /Market Evidence/ }));
    expect(screen.getByLabelText("需求引用")).toHaveValue("demand:kept");
  });

  it("supports arrow, Home, and End keyboard navigation with roving focus", () => {
    render(<ProductStudioWorkspace />);
    const demand = screen.getByRole("tab", { name: /Demand/ });
    demand.focus();
    fireEvent.keyDown(demand, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: /Market Evidence/ })).toHaveFocus();
    expect(screen.getByRole("tab", { name: /Market Evidence/ })).toHaveAttribute("aria-selected", "true");

    fireEvent.keyDown(screen.getByRole("tab", { name: /Market Evidence/ }), { key: "End" });
    expect(screen.getByRole("tab", { name: /Sandbox/ })).toHaveFocus();
    expect(screen.getByRole("tabpanel")).toHaveAccessibleName(/Sandbox/);

    fireEvent.keyDown(screen.getByRole("tab", { name: /Sandbox/ }), { key: "Home" });
    expect(demand).toHaveFocus();
    fireEvent.keyDown(demand, { key: "ArrowLeft" });
    expect(screen.getByRole("tab", { name: /Sandbox/ })).toHaveFocus();
  });

  it("makes every stage title reachable from its tab", async () => {
    render(<ProductStudioWorkspace />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: /Market Evidence/ }));
    expect(screen.getByRole("heading", { name: "市场与竞品证据工作台" })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /Concept Decision/ }));
    expect(screen.getByRole("heading", { name: "产品概念候选决策台" })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /PDM Review/ }));
    expect(screen.getByRole("heading", { name: "PDM 人工评审队列" })).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /Sandbox/ }));
    expect(screen.getByRole("heading", { name: "产品设计工厂" })).toBeInTheDocument();
  });
});
