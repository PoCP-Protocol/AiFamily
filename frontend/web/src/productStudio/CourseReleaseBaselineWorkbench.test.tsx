import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CourseReleaseBaselineWorkbench } from "./CourseReleaseBaselineWorkbench";

describe("CourseReleaseBaselineWorkbench", () => {
  it("renders an immutable 24 lesson BOM and keeps release disabled", () => {
    render(<CourseReleaseBaselineWorkbench />);
    expect(screen.getByRole("heading", { name: "课程发布基线与课件 BOM" })).toBeInTheDocument();
    expect(within(screen.getByLabelText("24课时发布 BOM 导航")).getAllByRole("button")).toHaveLength(24);
    expect(screen.getByText("0/24 已绑定")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "提交人工发布门禁" })).toBeDisabled();
  });

  it("preserves lesson bindings and reports the first incomplete BOM position", async () => {
    const user = userEvent.setup();
    render(<CourseReleaseBaselineWorkbench />);
    await user.type(screen.getByLabelText("Lesson 版本引用"), "lesson:one@v1");
    const rail = screen.getByLabelText("24课时发布 BOM 导航");
    await user.click(within(rail).getByRole("button", { name: "2" }));
    await user.click(within(rail).getByRole("button", { name: "1" }));
    expect(screen.getByLabelText("Lesson 版本引用")).toHaveValue("lesson:one@v1");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "编译发布基线 DRAFT" }));
    expect(screen.getByRole("alert")).toHaveTextContent("发布基线未通过");
  });
});
