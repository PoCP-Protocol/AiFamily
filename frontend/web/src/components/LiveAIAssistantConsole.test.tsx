import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LiveAIAssistantConsole } from "./LiveAIAssistantConsole";

afterEach(() => vi.unstubAllGlobals());

describe("LiveAIAssistantConsole", () => {
  it("fails closed without a sandbox provider", () => {
    render(<LiveAIAssistantConsole />);
    expect(screen.getByRole("alert")).toHaveTextContent("AI Sandbox 未连接");
    expect(screen.queryByRole("button", { name: "生成 AI 草案" })).not.toBeInTheDocument();
  });

  it("generates a draft and records a human edit", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(draft("DRAFT")))
      .mockResolvedValueOnce(response(draft("EDITED_DRAFT", "人工修订：摘要草案")));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<LiveAIAssistantConsole aiBaseUrl="http://127.0.0.1:55305" />);

    await user.click(screen.getByRole("button", { name: "生成 AI 草案" }));
    expect(await screen.findByText("摘要草案")).toBeInTheDocument();
    expect(screen.getByText("问题场景")).toBeInTheDocument();
    expect(screen.getByText("需人工核对")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "人工编辑后保留" }));
    expect(await screen.findByText("人工修订：摘要草案")).toBeInTheDocument();
    expect(screen.getByText("EDITED_DRAFT")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("does not render an unsafe response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({
      ...draft("DRAFT"),
      fact_write: true,
    })));
    const user = userEvent.setup();
    render(<LiveAIAssistantConsole aiBaseUrl="http://127.0.0.1:55305" />);
    await user.click(screen.getByRole("button", { name: "生成 AI 草案" }));
    expect(await screen.findByText("生成已停止，没有产生草案或外部效果。")).toBeInTheDocument();
    expect(screen.queryByLabelText("AI 直播草案")).not.toBeInTheDocument();
  });
});

function response(payload: unknown) {
  return { ok: true, json: async () => payload } as Response;
}

function draft(status: string, summary = "摘要草案") {
  return {
    draft_ref: "draft.synthetic.1",
    summary,
    chapters: ["问题场景", "专家方法"],
    risk_flags: ["需人工核对"],
    status,
    provenance_ref: "provenance.synthetic.1",
    draft_hash: "hash",
    source: "SANDBOX_SYNTHETIC",
    fixture_only: true,
    external_effect: false,
    fact_write: false,
  };
}
