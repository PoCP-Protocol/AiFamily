import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CourseContentWorkbench } from "./CourseContentWorkbench";

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
});
