import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ProductStudioApiError } from "./api";
import { CourseContentWorkbench } from "./CourseContentWorkbench";
import { completeCourseInput, courseDraftResponse } from "./courseContentAuthoringTestFixture";
import { createCourseContentTemplate } from "./courseContentTemplate";

describe("CourseContentWorkbench", () => {
  it("renders a 24 lesson contract-preview workflow without publish controls", () => {
    render(<CourseContentWorkbench contractPreview />);
    expect(screen.getByRole("heading", { name: "24 课时课程与课件编排" })).toBeInTheDocument();
    expect(within(screen.getByLabelText("24 课时导航")).getAllByRole("button")).toHaveLength(24);
    expect(screen.getByText("0/24 已完整")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存 CourseContent DRAFT" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /发布|评审通过/ })).not.toBeInTheDocument();
  });

  it("keeps lesson edits while navigating and reports incomplete compilation", async () => {
    const user = userEvent.setup();
    render(<CourseContentWorkbench contractPreview />);
    await user.type(screen.getByLabelText("课时标题"), "建立共同目标");
    const rail = screen.getByLabelText("24 课时导航");
    await user.click(within(rail).getByRole("button", { name: /2 第 2 节/ }));
    await user.type(screen.getByLabelText("课时标题"), "识别沟通障碍");
    await user.click(within(rail).getByRole("button", { name: /1 建立共同目标/ }));
    expect(screen.getByLabelText("课时标题")).toHaveValue("建立共同目标");

    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "编译 24 课时合同预览" }));
    expect(screen.getByRole("alert")).toHaveTextContent("请完整填写课程总纲");
  });

  it("creates once, reads back, and reports only DRAFT persistence", async () => {
    const input = completeCourseInput();
    const initialState = createCourseContentTemplate();
    Object.assign(initialState, {
      ...input,
      assessment_criteria: input.assessment_criteria.join("\n"),
      outcome_metrics: input.outcome_metrics.join("\n"),
      content_accuracy_claim_refs: input.content_accuracy_claim_refs.join("\n"),
    });
    const response = courseDraftResponse();
    const client = {
      createDraft: vi.fn().mockResolvedValue(response),
      getDraft: vi.fn().mockResolvedValue(response),
    };
    render(<CourseContentWorkbench client={client} initialState={initialState} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "编译 24 课时合同预览" }));
    await user.click(screen.getByRole("button", { name: "保存 CourseContent DRAFT" }));
    expect(client.createDraft).toHaveBeenCalledTimes(1);
    expect(client.getDraft).toHaveBeenCalledWith(response.id);
    expect(screen.getByRole("status")).toHaveTextContent("DRAFT 已创建并完成持久化回读");
    expect(screen.getByRole("status")).toHaveTextContent("不是评审通过或发布结果");
  });

  it("retries only GET after readback failure and locks an unknown POST outcome", async () => {
    const input = completeCourseInput();
    const initialState = createCourseContentTemplate();
    Object.assign(initialState, {
      ...input,
      assessment_criteria: input.assessment_criteria.join("\n"),
      outcome_metrics: input.outcome_metrics.join("\n"),
      content_accuracy_claim_refs: input.content_accuracy_claim_refs.join("\n"),
    });
    const response = courseDraftResponse();
    const readbackClient = {
      createDraft: vi.fn().mockResolvedValue(response),
      getDraft: vi.fn().mockRejectedValueOnce(new ProductStudioApiError("TIMEOUT", "回读超时")).mockResolvedValue(response),
    };
    const user = userEvent.setup();
    const view = render(<CourseContentWorkbench client={readbackClient} initialState={initialState} />);
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "编译 24 课时合同预览" }));
    await user.click(screen.getByRole("button", { name: "保存 CourseContent DRAFT" }));
    await user.click(screen.getByRole("button", { name: "重试持久化回读" }));
    expect(readbackClient.createDraft).toHaveBeenCalledTimes(1);
    expect(readbackClient.getDraft).toHaveBeenCalledTimes(2);
    view.unmount();

    const unknownClient = {
      createDraft: vi.fn().mockRejectedValue(new ProductStudioApiError("UNKNOWN_OUTCOME", "结果未知")),
      getDraft: vi.fn(),
    };
    render(<CourseContentWorkbench client={unknownClient} initialState={initialState} />);
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "编译 24 课时合同预览" }));
    await user.click(screen.getByRole("button", { name: "保存 CourseContent DRAFT" }));
    expect(screen.getByRole("alert")).toHaveTextContent("不提供重试按钮");
    expect(screen.getByRole("button", { name: "保存 CourseContent DRAFT" })).toBeDisabled();
    expect(unknownClient.createDraft).toHaveBeenCalledTimes(1);
  });
});
