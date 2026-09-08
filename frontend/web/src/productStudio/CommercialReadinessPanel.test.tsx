import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CommercialReadinessPanel } from "./CommercialReadinessPanel";

describe("CommercialReadinessPanel", () => {
  it("shows explicit blockers returned by the readiness API", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ready: false,
      checks: {
        lessons_24: true,
        payment_sandbox_verified: false,
      },
      blockers: ["payment_sandbox_verified"],
    }), { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchImpl);

    render(<CommercialReadinessPanel />);
    await userEvent.setup().click(screen.getByRole("button", { name: "评估当前证据" }));

    expect(await screen.findByText("暂不可商业化")).toBeInTheDocument();
    expect(screen.getByText(/支付沙箱已验证/)).toBeInTheDocument();
    expect(fetchImpl).toHaveBeenCalledOnce();
  });
});
