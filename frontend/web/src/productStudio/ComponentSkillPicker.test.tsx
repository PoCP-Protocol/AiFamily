import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ComponentSkillPicker } from "./ComponentSkillPicker";
import { sampleCatalogSnapshot } from "./productPortfolioFixtures";

describe("ComponentSkillPicker", () => {
  it("does not invent catalog items when no trusted snapshot exists", () => {
    render(<ComponentSkillPicker catalog={null} onSelectionChange={vi.fn()} selection={null} />);
    expect(screen.getByRole("note")).toHaveTextContent("Catalog Snapshot 尚未接入");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("selects only an applicable published current exact version", async () => {
    const onSelectionChange = vi.fn();
    render(<ComponentSkillPicker catalog={sampleCatalogSnapshot} now={() => Date.parse("2026-09-02T00:00:00Z")} onSelectionChange={onSelectionChange} selection={null} />);

    const reusable = screen.getByRole("checkbox", { name: /可暂停的今日行动/ });
    const blocked = screen.getByRole("checkbox", { name: /青少年自主对话/ });
    expect(reusable).toBeEnabled();
    expect(blocked).toBeDisabled();
    expect(screen.getByText("AGE_MISMATCH、SCENARIO_MISMATCH")).toBeInTheDocument();

    await userEvent.setup().click(reusable);
    expect(onSelectionChange).toHaveBeenCalledWith(expect.objectContaining({
      catalog_snapshot_id: sampleCatalogSnapshot.snapshot_id,
      component_refs: ["component:action:v1"],
      skill_refs: [],
    }));
    expect(screen.queryByRole("columnheader", { name: /得分|排名/i })).not.toBeInTheDocument();
  });

  it("filters by server-declared target fields without changing eligibility", async () => {
    render(<ComponentSkillPicker catalog={sampleCatalogSnapshot} now={() => Date.parse("2026-09-02T00:00:00Z")} onSelectionChange={vi.fn()} selection={null} />);
    await userEvent.setup().selectOptions(screen.getByLabelText("年龄段"), "AGE_13_15");
    expect(screen.getByText("青少年自主对话")).toBeInTheDocument();
    expect(screen.queryByText("可暂停的今日行动")).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /青少年自主对话/ })).toBeDisabled();
  });

  it("fails closed without crashing when the snapshot is malformed", () => {
    render(<ComponentSkillPicker catalog={{ items: [null] } as never} onSelectionChange={vi.fn()} selection={null} />);
    expect(screen.getByRole("alert")).toHaveTextContent("INVALID_CATALOG_SNAPSHOT");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
  });

  it("keeps selection read-only after expiry or snapshot drift", async () => {
    const onSelectionChange = vi.fn();
    const selection = {
      catalog_snapshot_id: "catalog-snapshot:old",
      catalog_content_hash: "0".repeat(64),
      target_context_hash: sampleCatalogSnapshot.target_context_hash,
      component_refs: ["component:action:v1"],
      skill_refs: [],
    };
    render(<ComponentSkillPicker catalog={sampleCatalogSnapshot} now={() => Date.parse("2100-01-01T00:00:00Z")} onSelectionChange={onSelectionChange} selection={selection} />);
    expect(screen.getByText("CATALOG_SNAPSHOT_INACTIVE")).toBeInTheDocument();
    expect(screen.getByText("CATALOG_SNAPSHOT_DRIFTED")).toBeInTheDocument();
    const selected = screen.getByRole("checkbox", { name: /可暂停的今日行动/ });
    expect(selected).toBeChecked();
    expect(selected).toBeDisabled();
    await userEvent.setup().click(selected);
    expect(onSelectionChange).not.toHaveBeenCalled();
  });
});
