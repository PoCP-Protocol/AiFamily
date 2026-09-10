import { fireEvent, render, screen, within, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CourseSystemBlueprintPanel } from "./CourseSystemBlueprintPanel";
import { COURSE_SYSTEM_STAGES } from "./courseSystemBlueprint";
import type { CourseContentReadApiClient } from "./courseContentApi";
import type { CourseDeliveryProjectionApiClient } from "./courseDeliveryProjectionApi";

describe("CourseSystemBlueprintPanel", () => {
  it("filters lessons by stage and governance reason", async () => {
    const client = {
      get: async () => ({
        system_id: "course-system:family-growth",
        version: "v1",
        product_package_version_ref: "package@v1",
        stages: [...COURSE_SYSTEM_STAGES],
        bom_lesson_sequences: [1],
        bom_lesson_statuses: { 1: { qa_status: "APPROVED", rights_status: "CLEARED", safety_status: "CLEARED" } },
      }),
    };
    render(<CourseSystemBlueprintPanel client={client} />);
    const list = await screen.findByRole("list", { name: "24课时交付清单" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(24);
    fireEvent.click(screen.getByRole("button", { name: /S1 · 家庭觉察/ }));
    expect(within(list).getAllByRole("listitem")).toHaveLength(4);
    fireEvent.click(screen.getByRole("button", { name: "NO_ASSET" }));
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "清除原因筛选" }));
    expect(within(list).getAllByRole("listitem")).toHaveLength(4);
    fireEvent.click(screen.getByRole("button", { name: /缺资产 23/ }));
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "清除全部筛选" }));
    expect(within(list).getAllByRole("listitem")).toHaveLength(24);
  });

  it("selects a published course and loads its delivery projection", async () => {
    const courseContentClient: CourseContentReadApiClient = {
      listPublished: async () => [{
        id: "course-24", version: 1, status: "PUBLISHED", tenant_scope: "dev", created_by: "author",
        created_at: "2026-01-01", updated_at: "2026-01-01", title: "家庭成长24课",
        product_component_id: null, course_system_version_ref: "course-system:family-growth@v1",
        problem_statement: "问题", assessment_criteria: ["标准"], learning_goal: "目标", lessons: [],
        ai_coach_prompt_ref: null, review_cadence: "每周", outcome_metrics: ["指标"],
        content_accuracy_claim_refs: ["claim"], reviewed_by: "reviewer", reviewed_at: "2026-01-01",
        review_reason: "通过", published_at: "2026-01-01",
      }],
      get: async () => { throw new Error("unused"); },
    };
    const deliveryClient: CourseDeliveryProjectionApiClient = {
      get: async (id) => ({ course_content_id: id, course_system_version_ref: "course-system:family-growth@v1", product_component_id: null, lessons: [], ready_lessons: 24, blocked_lessons: 0, publishable_to_service: true }),
    };
    render(<CourseSystemBlueprintPanel client={{ get: async () => ({ system_id: "course-system:family-growth", version: "v1", product_package_version_ref: "package@v1", stages: [...COURSE_SYSTEM_STAGES], bom_lesson_sequences: [], bom_lesson_statuses: {} }) }} courseContentClient={courseContentClient} deliveryClient={deliveryClient} />);
    expect(await screen.findByText(/24\/24 节已具备服务交付条件/)).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "选择已发布课程" })).toHaveValue("course-24");
  });

  it("does not load course data while the workspace tab is inactive", () => {
    let calls = 0;
    const blocked = async () => { calls += 1; throw new Error("should not load"); };
    render(<CourseSystemBlueprintPanel enabled={false} client={{ get: blocked }} courseContentClient={{ listPublished: blocked, get: blocked }} deliveryClient={{ get: blocked }} />);
    expect(calls).toBe(0);
  });

  it("shows a visible error when the published course directory fails", async () => {
    let attempts = 0;
    render(<CourseSystemBlueprintPanel enabled courseContentClient={{ listPublished: async () => { attempts += 1; if (attempts === 1) throw new Error("offline"); return []; }, get: async () => { throw new Error("unused"); } }} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("已发布课程目录暂不可读取");
    fireEvent.click(await screen.findByRole("button", { name: "重试读取课程目录" }));
    await waitFor(() => expect(screen.getByText("尚未读取已发布课程交付投影。")).toBeInTheDocument());
    expect(attempts).toBe(2);
  });

});
