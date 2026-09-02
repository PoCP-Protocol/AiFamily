import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LiveIncidentConsole } from "./LiveIncidentConsole";

afterEach(() => vi.unstubAllGlobals());

describe("LiveIncidentConsole", () => {
  it("fails closed without the incident provider", () => {
    render(<LiveIncidentConsole />);
    expect(screen.getByText("安全事件服务暂未连接。")).toBeInTheDocument();
  });

  it("lets only the human console submit a stop decision", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response([incident("PENDING")]))
      .mockResolvedValueOnce(response(incident("STOPPED")));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<LiveIncidentConsole incidentBaseUrl="http://127.0.0.1:55306" />);
    expect(await screen.findByText("成人请求人工核对")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "人工停播" }));
    expect(await screen.findByText("当前没有待处理举报")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

function response(payload: unknown) {
  return { ok: true, json: async () => payload } as Response;
}

function incident(state: string) {
  return {
    report_ref: "incident.synthetic.1",
    session_ref: "media.synthetic.1",
    reason: "成人请求人工核对",
    state,
    source: "SANDBOX_SYNTHETIC",
    fixture_only: true,
    external_effect: false,
  };
}
