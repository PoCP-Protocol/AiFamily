import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CommerceProjectionPanel } from "./CommerceProjectionPanel";
import type { CommerceProjectionApiClient } from "./commerceProjectionApi";

const projection = {
  family_id: "family-demo",
  projection_version: 2,
  visibility: "FAMILY_PRIVATE" as const,
  read_only: true as const,
  order_intents: [{ order_intent_id: "order-1", status: "SUBMITTED", product_ref: "PRODUCT_21D", product_version: 1, created_at: "2026-09-09T00:00:00Z" }],
  entitlements: [{ entitlement_id: "ent-1", status: "REVOKED", source_order_intent_id: "order-1", available_at: null, expires_at: null }],
  text_equivalent: "退款恢复后权益已撤销。",
};

describe("CommerceProjectionPanel", () => {
  it("reads and renders the read-only delivery projection", async () => {
    const client: CommerceProjectionApiClient = { get: vi.fn().mockResolvedValue(projection) };
    render(<CommerceProjectionPanel client={client} />);
    fireEvent.click(screen.getByRole("button", { name: "读取交付状态" }));
    await waitFor(() => expect(screen.getByText("退款恢复后权益已撤销。")).toBeInTheDocument());
    expect(screen.getByText(/只读投影/)).toBeInTheDocument();
    expect(screen.getByText("PRODUCT_21D")).toBeInTheDocument();
    expect(screen.getByText(/SUBMITTED/)).toBeInTheDocument();
    expect(screen.getByText("ent-1")).toBeInTheDocument();
    expect(screen.getByText(/REVOKED/)).toBeInTheDocument();
    expect(client.get).toHaveBeenCalledWith("family-demo");
  });

  it("shows a fail-closed error when the projection is forbidden", async () => {
    const client: CommerceProjectionApiClient = { get: vi.fn().mockRejectedValue(new Error("家庭商业交付投影暂不可读取。")) };
    render(<CommerceProjectionPanel client={client} />);
    fireEvent.click(screen.getByRole("button", { name: "读取交付状态" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("暂不可读取");
  });
});
