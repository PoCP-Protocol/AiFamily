import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  COMPILER_CHECK_ORDER,
  CompilerReportPanel,
  normalizeCompilerReport,
  type CompilerReportInput,
} from "./CompilerReportPanel";

const completeReport = (overrides: Partial<Record<(typeof COMPILER_CHECK_ORDER)[number], { passed: boolean; detail: string }>> = {}): CompilerReportInput => ({
  passed: true,
  checks: Object.fromEntries(
    COMPILER_CHECK_ORDER.map((name) => [name, overrides[name] ?? { passed: true, detail: `${name} 已通过` }]),
  ),
});

describe("CompilerReportPanel", () => {
  it("renders all twelve checks in the stable IPD order", () => {
    render(<CompilerReportPanel report={completeReport()} />);

    const list = screen.getByRole("list", { name: "Compiler checks" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(12);
    expect(rows.map((row) => row.getAttribute("data-check-name"))).toEqual([...COMPILER_CHECK_ORDER]);
    expect(screen.getByText("PASS", { selector: ".compiler-overall strong" })).toBeInTheDocument();
    expect(screen.getByText("可提交 Human Gate 审查")).toBeInTheDocument();
  });

  it("shows a failed check and blocks entry to Human Gate", () => {
    render(
      <CompilerReportPanel
        report={completeReport({ check_safety: { passed: false, detail: "安全边界证据不足" } })}
      />,
    );

    const safety = screen.getByRole("listitem", { name: /Safety/ });
    expect(safety).toHaveTextContent("FAIL");
    expect(safety).toHaveTextContent("安全边界证据不足");
    expect(screen.getByText("不可进入 Human Gate")).toBeInTheDocument();
  });

  it("fails closed when the report is empty", () => {
    render(<CompilerReportPanel />);

    expect(screen.getByText("不可进入 Human Gate")).toBeInTheDocument();
    expect(screen.getAllByText("FAIL").length).toBeGreaterThanOrEqual(13);
    expect(screen.getByText("检查缺失：check_schema")).toBeInTheDocument();
  });

  it("fails closed when a check is missing even if overall passed is true", () => {
    const report = completeReport();
    delete report.checks?.check_cost;

    const normalized = normalizeCompilerReport(report);
    expect(normalized.passed).toBe(false);
    expect(normalized.hasMissingChecks).toBe(true);
    render(<CompilerReportPanel report={report} />);
    expect(screen.getByRole("listitem", { name: /Cost/ })).toHaveTextContent("检查缺失：check_cost");
    expect(screen.getByText("不可进入 Human Gate")).toBeInTheDocument();
  });

  it("fails closed for malformed or empty check details", () => {
    const report = completeReport({ check_evaluation: { passed: true, detail: "   " } });
    render(<CompilerReportPanel report={report} />);

    expect(screen.getByRole("listitem", { name: /Evaluation/ })).toHaveTextContent("FAIL");
    expect(screen.getByText("检查详情缺失")).toBeInTheDocument();
    expect(screen.getByText("不可进入 Human Gate")).toBeInTheDocument();
  });

  it("does not expose actions or automatic progression controls", () => {
    render(<CompilerReportPanel report={completeReport()} />);

    expect(screen.getByText(/只读报告/)).toHaveTextContent("不会自动推进阶段");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("requires the explicit overall passed flag", () => {
    const report = completeReport();
    report.passed = false;
    render(<CompilerReportPanel report={report} />);

    expect(screen.getByText("不可进入 Human Gate")).toBeInTheDocument();
  });
});

