import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ProductDefinitionOperatorReviewWorkbench } from "./ProductDefinitionOperatorReviewWorkbench";
import type {
  OperatorReviewApiClient,
  ProductDefinitionReviewTask,
} from "./operatorReviewApi";

const openTask: ProductDefinitionReviewTask = {
  task_id: "human-task:one",
  status: "OPEN",
  proposal_id: "proposal:one",
  draft_id: "decision-draft:one",
  action_name: "ADOPT_PRODUCT_CONCEPT_AS_DEFINITION",
  action_arguments: {
    concept_id: "concept:one",
    zone_assessment_id: "assessment:one",
    source_decision_draft_ref: "decision-draft:one",
    product_kind: "MICRO_CAMP",
    duration_days: 21,
    primary_contradiction: "理解与行动之间存在断点",
    demand_ref: "demand:one",
    market_insight_refs: ["insight:one"],
    component_ids: ["component:action:v1"],
    skill_ids: ["skill:reflection:v1"],
    success_metric_ids: ["metric:completion:v1"],
    guardrail_ids: ["guardrail:no-ranking:v1"],
    stop_conditions: ["guardian_requests_stop"],
    pause_policy: "guardian_can_pause",
    human_gate_policy: "operator_review_required",
  },
  risk_level: "MEDIUM",
  provenance_ref: "model-draft:one",
  created_at: "2026-09-01T09:00:00Z",
  expires_at: "2099-09-02T09:00:00Z",
  etag: '"etag-one"',
  decision_id: null,
  decision_outcome: null,
  decision_reason: null,
  decided_at: null,
  request_id: null,
};

describe("ProductDefinitionOperatorReviewWorkbench", () => {
  it("requires explicit reason and confirmation, then reports execution as pending", async () => {
    const decided = {
      ...openTask,
      status: "DECIDED" as const,
      decision_id: "decision:server",
      decision_outcome: "ACCEPT" as const,
      decision_reason: "证据足以进入 PDM 草案",
      decided_at: "2026-09-01T10:00:00Z",
      request_id: "named-action-request:server",
    };
    const client: OperatorReviewApiClient = {
      listOpenTasks: vi.fn().mockResolvedValue([openTask]),
      getTask: vi.fn().mockResolvedValue(openTask),
      decide: vi.fn().mockResolvedValue({
        task: decided,
        actor_id: "operator:server",
        execution_status: "PENDING",
      }),
    };
    const user = userEvent.setup();
    render(<ProductDefinitionOperatorReviewWorkbench client={client} />);

    await user.click(screen.getByRole("button", { name: "刷新待评审任务" }));
    await user.click(screen.getByRole("button", { name: /human-task:one/ }));
    expect(screen.getByText("model-draft:one")).toBeInTheDocument();
    const prepare = screen.getByRole("button", { name: /准备：接受/ });
    expect(prepare).toBeDisabled();

    await user.type(screen.getByLabelText("人工决策理由"), "证据足以进入 PDM 草案");
    await user.click(prepare);
    expect(client.decide).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "确认提交人工决定" }));

    expect(client.decide).toHaveBeenCalledWith(
      openTask,
      "ACCEPT",
      "证据足以进入 PDM 草案",
      expect.stringContaining("product-definition-review:human-task:one:"),
    );
    expect(screen.getByText(/尚不代表 ProductDefinition 已创建/)).toBeInTheDocument();
    expect(screen.getByText(/operator:server/)).toBeInTheDocument();
  });

  it("clears stale queue data before a failed refresh", async () => {
    const client: OperatorReviewApiClient = {
      listOpenTasks: vi.fn()
        .mockResolvedValueOnce([openTask])
        .mockRejectedValueOnce(new Error("offline")),
      getTask: vi.fn(),
      decide: vi.fn(),
    };
    const user = userEvent.setup();
    render(<ProductDefinitionOperatorReviewWorkbench client={client} />);

    await user.click(screen.getByRole("button", { name: "刷新待评审任务" }));
    expect(screen.getByRole("button", { name: /human-task:one/ })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "刷新待评审任务" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("INVALID_RESPONSE");
    expect(screen.queryByRole("button", { name: /human-task:one/ })).not.toBeInTheDocument();
  });
});
