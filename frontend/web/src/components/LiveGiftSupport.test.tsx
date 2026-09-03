import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LiveGiftSupport } from "./LiveGiftSupport";

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe("LiveGiftSupport", () => {
  it("records and reverses an adult-only synthetic gift with split evidence", async () => {
    let purchaseRef = "";
    const fetchMock = vi.fn().mockImplementation(async (input: string, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/purchases")) {
        const payload = JSON.parse(String(init?.body));
        purchaseRef = payload.purchase_ref;
        expect(payload).toMatchObject({
          track: "CONTENT_SUPPORT",
          subject_ref: "gift.synthetic.companionship",
          amount: 500,
          currency: "CNY_CENT",
        });
        return response({ purchase_ref: purchaseRef, track: "CONTENT_SUPPORT", ...envelope() });
      }
      if (url.endsWith("/reversals")) return response({ purchase_ref: purchaseRef, ...envelope() });
      const reversed = fetchMock.mock.calls.some(([calledUrl]) => String(calledUrl).endsWith("/reversals"));
      if (url.endsWith("/balances")) {
        return response({ purchase_ref: purchaseRef, cash: reversed ? 0 : 500, settlement: reversed ? 0 : 500, entitlement: reversed ? "REVOKED" : "ACTIVE", ...envelope() });
      }
      return response({
        purchase_ref: purchaseRef,
        track: "CONTENT_SUPPORT",
        currency: "CNY_CENT",
        entitlement: reversed ? "REVOKED" : "ACTIVE",
        beneficiaries: reversed ? [] : [
          { beneficiary_ref: "expert.synthetic.1", net_amount: 400 },
          { beneficiary_ref: "platform:aifamily", net_amount: 100 },
        ],
        total: reversed ? 0 : 500,
        ...envelope(),
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<LiveGiftSupport commerceBaseUrl="http://127.0.0.1:55400" />);

    await user.click(screen.getByRole("button", { name: /陪伴花束/ }));
    await user.click(screen.getByRole("button", { name: "赠送陪伴花束（演示）" }));

    expect(await screen.findByText("陪伴花束已送达（演示），没有真实扣款。")).toBeInTheDocument();
    expect(screen.getByText(/专家 ¥4.00 · 平台 ¥1.00/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "撤销礼物演示记录" }));
    expect(await screen.findByText("礼物记录已撤销，待结算归零。")).toBeInTheDocument();
  });

  it("fails closed without a local commerce adapter", () => {
    render(<LiveGiftSupport commerceBaseUrl="https://commerce.example" />);
    expect(screen.getByRole("button", { name: "赠送小橘灯（演示）" })).toBeDisabled();
  });
});

function envelope() {
  return { source: "SANDBOX_SYNTHETIC", fixture_only: true, external_effect: false };
}

function response(payload: unknown) {
  return { ok: true, json: async () => payload } as Response;
}
