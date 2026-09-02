import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LiveModeratorConsole } from "./LiveModeratorConsole";

afterEach(() => vi.unstubAllGlobals());

describe("LiveModeratorConsole", () => {
  it("collects pending questions across active control-plane sessions", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          {
            session_ref: "live.synthetic.one",
            approval_status: "APPROVED",
            status: "LIVE",
            source: "SANDBOX_SYNTHETIC",
            fixture_only: true,
          },
          {
            session_ref: "live.synthetic.two",
            approval_status: "APPROVED",
            status: "SCHEDULED",
            source: "SANDBOX_SYNTHETIC",
            fixture_only: true,
          },
        ],
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [{
          question_ref: "question.one",
          session_ref: "live.synthetic.one",
          text: "怎样先听懂对方？",
          status: "PENDING",
          source: "SANDBOX_SYNTHETIC",
          fixture_only: true,
        }],
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [{
          question_ref: "question.two",
          session_ref: "live.synthetic.two",
          text: "冲突后如何重新开始？",
          status: "PENDING",
          source: "SANDBOX_SYNTHETIC",
          fixture_only: true,
        }],
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          question_ref: "question.one",
          session_ref: "live.synthetic.one",
          text: "怎样先听懂对方？",
          status: "APPROVED",
          source: "SANDBOX_SYNTHETIC",
          fixture_only: true,
        }),
      });
    vi.stubGlobal("fetch", fetchMock);
    render(
      <LiveModeratorConsole
        interactionBaseUrl="http://127.0.0.1:55200"
        controlBaseUrl="http://127.0.0.1:55300"
      />,
    );

    expect(await screen.findByText("2 条待审核")).toBeInTheDocument();
    expect(screen.getByText(/live\.synthetic\.one/)).toBeInTheDocument();
    expect(screen.getByText(/live\.synthetic\.two/)).toBeInTheDocument();
    const firstCard = screen.getByText("怎样先听懂对方？").closest("article");
    await userEvent.setup().click(
      firstCard!.querySelector("button") as HTMLButtonElement,
    );
    expect(await screen.findByText("1 条待审核")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("fails closed when control-plane session evidence is unavailable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));
    render(
      <LiveModeratorConsole
        interactionBaseUrl="http://127.0.0.1:55200"
        controlBaseUrl="http://127.0.0.1:55300"
      />,
    );
    expect(await screen.findByText("审核队列读取失败，请稍后重试。")).toBeInTheDocument();
  });
});
