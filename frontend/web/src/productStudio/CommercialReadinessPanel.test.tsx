import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CommercialReadinessPanel } from "./CommercialReadinessPanel";

describe("CommercialReadinessPanel", () => {
  it("shows explicit blockers returned by the readiness API", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ready: false,
      execution_mode: "EVALUATION_ONLY",
      evaluated_at: "2026-09-09T12:00:00Z",
      scope: "FULL_24",
      checks: {
        lesson_scope_valid: true,
        payment_sandbox_verified: false,
      },
      blockers: ["payment_sandbox_verified"],
      evidence_refs: ["evidence:payment-sandbox@v1"],
    }), { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchImpl);

    render(<CommercialReadinessPanel />);
    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: "证据引用" }), "evidence:payment-sandbox@v1");
    await user.click(screen.getByRole("button", { name: "评估当前证据" }));

    expect(await screen.findByText("暂不可商业化")).toBeInTheDocument();
    expect(screen.getByText(/EVALUATION_ONLY/)).toBeInTheDocument();
    expect(screen.getByText(/评估时间：/)).toBeInTheDocument();
    expect(screen.getByText(/支付沙箱已验证/)).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "商业化证据引用" })).getByText("evidence:payment-sandbox@v1")).toBeInTheDocument();
    expect(fetchImpl).toHaveBeenCalledOnce();
  });

  it("sends the four-lesson pilot scope to the readiness API", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ready: false,
      execution_mode: "EVALUATION_ONLY",
      evaluated_at: "2026-09-09T12:00:00Z",
      scope: "PILOT_21D",
      checks: { lesson_scope_valid: false },
      blockers: ["lesson_scope_valid"],
      evidence_refs: [],
    }), { status: 200, headers: { "content-type": "application/json" } }));
    vi.stubGlobal("fetch", fetchImpl);

    render(<CommercialReadinessPanel />);
    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: "证据引用" }), " evidence:pilot@v1 \nevidence:pilot@v1");
    await user.selectOptions(screen.getByRole("combobox", { name: "产品范围" }), "4");
    await user.click(screen.getByRole("button", { name: "评估当前证据" }));

    expect(await screen.findByText("21天成长营商业化就绪度")).toBeInTheDocument();
    expect(JSON.parse(fetchImpl.mock.calls[0][1].body as string).lesson_count).toBe(4);
    expect(JSON.parse(fetchImpl.mock.calls[0][1].body as string).evidence_refs).toEqual(["evidence:pilot@v1"]);
  });

  it("fails closed when the readiness contract contains a non-boolean check", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      ready: true,
      execution_mode: "EVALUATION_ONLY",
      evaluated_at: "2026-09-09T12:00:00Z",
      scope: "FULL_24",
      checks: { lesson_scope_valid: "true" },
      blockers: [],
      evidence_refs: [],
    }), { status: 200, headers: { "content-type": "application/json" } })));

    render(<CommercialReadinessPanel />);
    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: "证据引用" }), "evidence:contract@v1");
    await user.click(screen.getByRole("button", { name: "评估当前证据" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("commercial_readiness_invalid_response");
  });

  it("explains how to fix an invalid evidence reference", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{\"detail\":\"READINESS_EVIDENCE_REF_INVALID\"}", { status: 422 })));

    render(<CommercialReadinessPanel />);
    await userEvent.setup().click(screen.getByRole("button", { name: "评估当前证据" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("evidence:payment@v1");
  });

  it("rejects an invalid evidence reference before making a request", async () => {
    const fetchImpl = vi.fn();
    vi.stubGlobal("fetch", fetchImpl);
    render(<CommercialReadinessPanel />);
    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: "证据引用" }), "evidence:pilot");
    await user.click(screen.getByRole("button", { name: "评估当前证据" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("evidence:payment@v1");
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("sends operator-selected commerce evidence states", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ready: false, execution_mode: "EVALUATION_ONLY", evaluated_at: "2026-09-09T12:00:00Z", scope: "FULL_24", checks: { lesson_scope_valid: true }, blockers: [], evidence_refs: ["evidence:payment@v1"] }), { status: 200 }));
    vi.stubGlobal("fetch", fetchImpl);
    render(<CommercialReadinessPanel />);
    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: "证据引用" }), "evidence:payment@v1");
    await user.click(screen.getByLabelText("支付沙箱已验证"));
    await user.click(screen.getByRole("button", { name: "评估当前证据" }));
    const body = JSON.parse(fetchImpl.mock.calls[0][1].body as string);
    expect(body.payment_sandbox_verified).toBe(true);
  });
});
