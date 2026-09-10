import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { CommercialOfferDraftPanel } from "./CommercialOfferDraftPanel";

describe("CommercialOfferDraftPanel", () => {
  it("keeps the commercial proposal as a human-gated draft", async () => {
    render(<CommercialOfferDraftPanel />);
    await userEvent.setup().click(screen.getByRole("button", { name: "保存为 DRAFT 草案" }));
    expect(await screen.findByRole("status")).toHaveTextContent("DRAFT · 未发布");
    expect(screen.getByText(/不创建订单/)).toBeInTheDocument();
  });
});
