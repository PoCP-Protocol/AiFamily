import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { WebRoot } from "../main";

const originalPath = window.location.pathname;

afterEach(() => {
  window.history.replaceState({}, "", originalPath);
  vi.unstubAllGlobals();
});

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
    await userEvent.setup().click(screen.getByRole("tab", { name: /Course Content/ }));
    expect(screen.getByRole("heading", { name: "24 课时课程与课件编排" })).toBeInTheDocument();
    expect(screen.getByText(/内容准确性引用不等于证据已准入/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "家庭权益与退款恢复状态" })).toBeInTheDocument();
    expect(screen.getByText(/只读投影：不会收款、创建订单或修改权益/)).toBeInTheDocument();
    await userEvent.setup().click(screen.getByRole("tab", { name: /Sandbox/ }));
    expect(screen.getByRole("heading", { name: "产品设计工厂" })).toBeInTheDocument();
    expect(screen.getByTestId("product-studio-environment")).toHaveTextContent("Sandbox");
    expect(screen.getByText(/所有 AI 内容均为 DRAFT/)).toBeInTheDocument();
  }, 15_000);

  it("keeps the root path on Experience Studio", async () => {
    window.history.replaceState({}, "", "/");
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>(async (input) => {
        const path = new URL(String(input), window.location.origin).pathname;
        if (path === "/auth/account-session") {
          return new Response(JSON.stringify({ token: "dev-token", family_id: "family-a" }), { status: 200 });
        }
        if (path === "/families/family-a/ui/02/assessment") {
          return new Response(
            JSON.stringify({
              projection_version: "test-v1",
              availability: "READY",
              tool: {
                tool_ref: "tool-test",
                title: "家庭理解",
                items: [],
              },
              dimensions: [],
              subjects: [{ person_id: "person-a", display_name: "孩子" }],
              active_session: null,
            }),
            { status: 200 },
          );
        }
        return new Response(JSON.stringify({ detail: `Unexpected request: ${path}` }), { status: 404 });
      }),
    );
    render(<WebRoot />);
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /今天，先处理\s*一件事/ })).toBeInTheDocument();
      expect(screen.queryByText(/模型|生成通道|provider|DRAFT/i)).not.toBeInTheDocument();
    });
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
