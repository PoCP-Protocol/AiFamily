import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CourseContentGovernancePanel } from "./CourseContentGovernancePanel";
import { publishedCourse } from "./courseContentTestFixture";

describe("CourseContentGovernancePanel", () => {
  it("keeps the production workspace fail closed", () => {
    const client = { listPublished: vi.fn(), get: vi.fn() };
    render(<CourseContentGovernancePanel client={client} contractPreview />);
    expect(screen.getByRole("button", { name: "读取已发布课程" })).toBeDisabled();
    expect(screen.getByText(/不宣称24门课程已上线/)).toBeInTheDocument();
    expect(client.listPublished).not.toHaveBeenCalled();
  });

  it("shows published lessons and explicit governance gaps without scoring", async () => {
    const client = { listPublished: vi.fn().mockResolvedValue([publishedCourse]), get: vi.fn() };
    render(<CourseContentGovernancePanel client={client} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "读取已发布课程" }));
    expect(screen.getByText("1 门课程")).toBeInTheDocument();
    expect(screen.getByText("1 个课时")).toBeInTheDocument();
    expect(within(screen.getByLabelText("课程治理缺口")).getByText(/MISSING_FROM_CONTRACT/)).toBeInTheDocument();
    expect(screen.getByText(/claim:rhythm（仅引用，未证明 receipt admission）/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "共同定义问题" })).toBeInTheDocument();
    expect(screen.queryByText(/综合分|推荐排名/)).not.toBeInTheDocument();
  });
});
