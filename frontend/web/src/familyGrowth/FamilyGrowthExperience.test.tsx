import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FamilyGrowthExperience } from "./FamilyGrowthExperience";
import type { FamilyGrowthApiClient } from "./client";

describe("FamilyGrowthExperience", () => {
  it("carries a parent's own words into the controlled understanding request", async () => {
    const user = userEvent.setup();
    const createDraft = vi.fn(async (input: { payload: { expression: string } }) => ({
      run_id: "run-1",
      draft_version: "experience-draft.v1",
      status: "DRAFT" as const,
      output: { understanding: "你们都在努力让晚上顺利一些。", next_step: "先约定一个可以暂停的小步骤。" },
      limitations: ["这只是一个可以修改的理解。"],
      provenance: {
        provenance_ref: "provenance-1",
        kind: "SYNTHETIC_TEST" as const,
        model_attempt_ref: "attempt-1",
        context_snapshot_ref: "context-1",
        prompt_version: "family-companion.v1",
        schema_version: "family-experience-draft.v1",
        captured_at: "2026-09-09T00:00:00Z",
      },
      requires_human_confirmation: true as const,
      media_inputs: [],
      correlation_id: "correlation-1",
    }));

    const growthClient = {
      getAssessment: vi.fn(async () => ({
        projection_version: "test-v1",
        availability: "READY",
        tool: {
          tool_ref: "tool-1",
          title: "家庭理解",
          items: [{ item_ref: "FOCUS", response_type: "SINGLE_CHOICE" as const, required: true, options: ["学习习惯"] }],
        },
        dimensions: [],
        subjects: [{ person_id: "person-1", display_name: "孩子" }],
      })),
      startAssessment: vi.fn(async () => ({ session_id: "session-1", status: "ACTIVE" })),
      saveAssessmentResponse: vi.fn(async () => ({ session_id: "session-1", status: "RECORDED" })),
      submitAssessment: vi.fn(async () => ({ session_id: "session-1", status: "SUBMITTED" })),
      getGrowthHypothesis: vi.fn(async () => ({
        projection_version: "test-v1",
        availability: "READY",
        hypothesis: {
          hypothesis_ref: "hypothesis-1",
          title: "我们这样理解今晚的难处",
          statement: "你们都想让学习少一点拉扯。",
          need_refs: ["need-1"],
          action_candidate_refs: ["path-1"],
          evidence_refs: [],
        },
      })),
      decideGrowthHypothesis: vi.fn(async () => ({ session_id: "session-1", status: "CONFIRMED" })),
      getGrowthPath: vi.fn(),
    } as unknown as FamilyGrowthApiClient;

    render(
      <FamilyGrowthExperience
        growthClient={growthClient}
        experienceClient={{
          createDraft,
          decide: vi.fn(),
          submitFeedback: vi.fn(),
          requestHuman: vi.fn(),
          deleteRun: vi.fn(),
          replayRun: vi.fn(),
        }}
      />,
    );

    await user.click(await screen.findByRole("button", { name: /开始记录一件家庭难题/ }));
    const expression = screen.getByRole("textbox", { name: "补充说说最近发生了什么" });
    await user.clear(expression);
    await user.type(expression, "每天写作业前，我们都会开始催促，最后谁也不开心。");
    await user.click(screen.getByRole("button", { name: "学习习惯" }));
    await user.click(screen.getByRole("button", { name: /看见家庭理解/ }));
    await user.click(await screen.findByRole("button", { name: /继续决定下一步/ }));

    await waitFor(() => expect(createDraft).toHaveBeenCalledTimes(1));
    expect(createDraft.mock.calls[0][0].payload.expression).toContain("每天写作业前，我们都会开始催促");
    expect(screen.queryByText(/模型|生成通道|providerId|modelVersion/i)).not.toBeInTheDocument();
  });
});
