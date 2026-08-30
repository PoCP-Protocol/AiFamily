import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { LiveExperience } from "./LiveExperience";
import {
  LIVE_STATE_COPY,
  XIAO_JU_DENG_FIXTURE,
  resolveLiveView,
  type LiveViewState,
} from "../live/liveCatalog";

describe("Xiao Ju Deng read-only live UI", () => {
  it("shows the discovery card and the H-LIVE-01 detail fields", async () => {
    render(<LiveExperience environment={{ DEV: true }} />);
    expect(screen.getByText("小橘灯：家庭沟通中的温柔练习")).toBeInTheDocument();
    expect(screen.getByRole("article")).toHaveTextContent("小橘灯老师");

    await userEvent.setup().click(screen.getByRole("button", { name: "查看直播详情" }));

    expect(screen.getByText("H-LIVE-01 · 只读详情")).toBeInTheDocument();
    expect(screen.getByText("review:H-LIVE-01")).toBeInTheDocument();
    expect(screen.getByText("H-LIVE-01.v1")).toBeInTheDocument();
    expect(screen.getByText("true · DEV_ONLY")).toBeInTheDocument();
    expect(screen.getByText("APPROVED")).toBeInTheDocument();
    expect(screen.getByText("UNEXPIRED")).toBeInTheDocument();
    expect(screen.getByText("FAMILY")).toBeInTheDocument();
    expect(screen.getByRole("article")).toHaveTextContent("family-private");
    expect(screen.getByText("2026-08-30T18:00:00+08:00")).toBeInTheDocument();
    expect(XIAO_JU_DENG_FIXTURE.source).toBe("SANDBOX_SYNTHETIC");
    expect(XIAO_JU_DENG_FIXTURE.fixture_only).toBe(true);
  });

  it("keeps production fixture access fail-closed", () => {
    expect(resolveLiveView({ DEV: false })).toEqual({ state: "backend-missing", record: null });
    render(<LiveExperience environment={{ DEV: false }} />);
    expect(screen.getByText("后端未接入")).toBeInTheDocument();
    expect(screen.queryByText(XIAO_JU_DENG_FIXTURE.title)).not.toBeInTheDocument();
  });

  it.each<LiveViewState>([
    "loading",
    "empty",
    "denied",
    "withdrawn",
    "expired",
    "unauthorized",
    "forbidden",
    "not-found",
    "conflict",
    "error",
    "backend-missing",
    "provider-missing",
  ])("renders the %s state without a live action", (state) => {
    render(<LiveExperience viewModel={{ state, record: null }} />);
    expect(screen.getByText(LIVE_STATE_COPY[state].label)).toBeInTheDocument();
    expect(screen.getByText(LIVE_STATE_COPY[state].message)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("does not render prohibited room, token, child, score, or commerce fields", async () => {
    const { container } = render(<LiveExperience environment={{ DEV: true }} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "查看直播详情" }));
    const text = container.textContent?.toLowerCase() ?? "";
    for (const prohibited of ["room", "token", "画像", "排序", "分数", "购买", "预约", "观看"]) {
      expect(text).not.toContain(prohibited);
    }
  });
});
