import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CourseSystemBlueprintPanel } from "./CourseSystemBlueprintPanel";
import { COURSE_SYSTEM_STAGES } from "./courseSystemBlueprint";

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
});
