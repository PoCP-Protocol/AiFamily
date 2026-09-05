import type { ReactNode } from "react";

/**
 * Stable check order shared with the ProductCompiler.  Keeping this list in
 * the Web adapter means a report is rendered deterministically even when the
 * API serializes the checks as an unordered object.
 */
export const COMPILER_CHECK_ORDER = [
  "check_schema",
  "check_component",
  "check_compatibility",
  "check_workflow",
  "check_resource",
  "check_ai_use_case",
  "check_context_boundary",
  "check_safety",
  "check_human_gate",
  "check_cost",
  "check_evaluation",
  "check_sla",
] as const;

export type CompilerCheckName = (typeof COMPILER_CHECK_ORDER)[number];

export type CompilerCheck = {
  passed: boolean;
  detail: string;
  check_name?: string;
};

/** Input is deliberately read-only: this panel never mutates or persists it. */
export type CompilerReportInput = {
  checks?: Record<string, CompilerCheck | null | undefined>;
  passed?: boolean;
};

export type NormalizedCompilerCheck = {
  name: CompilerCheckName;
  label: string;
  passed: boolean;
  detail: string;
  missing: boolean;
};

export type NormalizedCompilerReport = {
  checks: NormalizedCompilerCheck[];
  passed: boolean;
  hasMissingChecks: boolean;
};

const CHECK_LABELS: Record<CompilerCheckName, string> = {
  check_schema: "Schema",
  check_component: "Component",
  check_compatibility: "Compatibility",
  check_workflow: "Workflow",
  check_resource: "Resource",
  check_ai_use_case: "AI Use Case",
  check_context_boundary: "Context Boundary",
  check_safety: "Safety",
  check_human_gate: "Human Gate",
  check_cost: "Cost",
  check_evaluation: "Evaluation",
  check_sla: "SLA",
};

const missingDetail = (name: CompilerCheckName) => `检查缺失：${name}`;

/**
 * Normalize untrusted API/fixture data with a fail-closed policy.  A report
 * cannot pass unless all twelve checks are present, well formed, and the
 * server's overall flag is explicitly true.
 */
export function normalizeCompilerReport(report?: CompilerReportInput | null): NormalizedCompilerReport {
  const checks = COMPILER_CHECK_ORDER.map((name) => {
    const candidate = report?.checks?.[name];
    const isWellFormed =
      candidate !== null &&
      typeof candidate === "object" &&
      typeof candidate.passed === "boolean" &&
      typeof candidate.detail === "string" &&
      candidate.detail.trim().length > 0;

    if (!isWellFormed) {
      return {
        name,
        label: CHECK_LABELS[name],
        passed: false,
        detail: candidate && typeof candidate === "object" && typeof candidate.detail === "string" && candidate.detail.trim().length === 0
          ? "检查详情缺失"
          : missingDetail(name),
        missing: true,
      } satisfies NormalizedCompilerCheck;
    }

    return {
      name,
      label: CHECK_LABELS[name],
      passed: candidate.passed,
      detail: candidate.detail,
      missing: false,
    } satisfies NormalizedCompilerCheck;
  });

  const hasMissingChecks = checks.some((check) => check.missing);
  const passed = report?.passed === true && !hasMissingChecks && checks.every((check) => check.passed);
  return { checks, passed, hasMissingChecks };
}

export type CompilerReportPanelProps = {
  report?: CompilerReportInput | null;
  footer?: ReactNode;
};

export function CompilerReportPanel({ report, footer }: CompilerReportPanelProps) {
  const normalized = normalizeCompilerReport(report);

  return (
    <section aria-label="Product Compiler Report" className="compiler-report-panel">
      <header>
        <h2>Product Compiler Report</h2>
        <p>按 IPD 编译顺序检查产品草案的可交付性。</p>
      </header>

      <div aria-live="polite" className={normalized.passed ? "compiler-overall pass" : "compiler-overall fail"}>
        <strong>{normalized.passed ? "PASS" : "FAIL"}</strong>
        <span>
          {normalized.passed ? "可提交 Human Gate 审查" : "不可进入 Human Gate"}
        </span>
      </div>

      <ol aria-label="Compiler checks">
        {normalized.checks.map((check) => (
          <li
            key={check.name}
            aria-label={`${check.label} ${check.passed ? "PASS" : "FAIL"}`}
            data-check-name={check.name}
          >
            <span aria-label={`${check.label} ${check.passed ? "PASS" : "FAIL"}`}>
              <strong>{check.passed ? "PASS" : "FAIL"}</strong> {check.label}
            </span>
            <span>{check.detail}</span>
          </li>
        ))}
      </ol>

      <p className="compiler-report-readonly">
        只读报告：不会自动推进阶段，也不会将 AI 输出写入事实。
      </p>
      {footer}
    </section>
  );
}
