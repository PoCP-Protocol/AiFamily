import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LiveReplayKnowledge } from "./LiveReplayKnowledge";

afterEach(() => vi.unstubAllGlobals());

describe("LiveReplayKnowledge", () => {
  it("shows only approved synthetic knowledge and lets the adult bookmark it", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response([approvedKnowledge()]))
      .mockResolvedValueOnce(response({
        bookmark_ref: "bookmark.ui.knowledge.synthetic.1",
        knowledge_ref: "knowledge.synthetic.1",
        replay_ref: "media.synthetic.1",
        actor_id: "actor.synthetic.adult",
        source: "SANDBOX_SYNTHETIC",
        fixture_only: true,
        external_effect: false,
      }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    render(
      <LiveReplayKnowledge
        baseUrl="http://127.0.0.1:55320"
        replayRef="media.synthetic.1"
      />,
    );
    expect(await screen.findByText("把冲突变成一次共同练习")).toBeInTheDocument();
    expect(screen.getByText("先听懂情绪")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "收藏这张知识卡" }));
    expect(await screen.findByRole("button", { name: "已收藏到家庭笔记" })).toBeDisabled();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it.each(["DRAFT", "REJECTED"])("fails closed when a %s item leaks from the provider", async (state) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response([{ ...approvedKnowledge(), state }])));
    render(
      <LiveReplayKnowledge
        baseUrl="http://127.0.0.1:55320"
        replayRef="media.synthetic.1"
      />,
    );
    expect(await screen.findByText("回放知识服务暂不可用，页面已安全关闭内容展示。")).toBeInTheDocument();
    expect(screen.queryByText("把冲突变成一次共同练习")).not.toBeInTheDocument();
  });

  it("fails closed for provider errors and non-local providers", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 503 } as Response);
    vi.stubGlobal("fetch", fetchMock);
    const { rerender } = render(
      <LiveReplayKnowledge
        baseUrl="http://127.0.0.1:55320"
        replayRef="media.synthetic.1"
      />,
    );
    expect(await screen.findByText("回放知识服务暂不可用，页面已安全关闭内容展示。")).toBeInTheDocument();
    rerender(
      <LiveReplayKnowledge
        baseUrl="https://production.example.com"
        replayRef="media.synthetic.1"
      />,
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("removes knowledge immediately when the replay deletion projection is observed", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response([approvedKnowledge()])));
    const { rerender } = render(
      <LiveReplayKnowledge
        baseUrl="http://127.0.0.1:55320"
        replayRef="media.synthetic.1"
      />,
    );
    expect(await screen.findByText("把冲突变成一次共同练习")).toBeInTheDocument();
    rerender(
      <LiveReplayKnowledge
        baseUrl="http://127.0.0.1:55320"
        replayRef="media.synthetic.1"
        replayDeleted
      />,
    );
    expect(screen.getByText("回放与衍生章节已删除，刷新或重启后不会恢复。")).toBeInTheDocument();
    expect(screen.queryByText("把冲突变成一次共同练习")).not.toBeInTheDocument();
  });
});

function response(payload: unknown): Response {
  return { ok: true, status: 200, json: async () => payload } as Response;
}

function approvedKnowledge() {
  return {
    knowledge_ref: "knowledge.synthetic.1",
    replay_ref: "media.synthetic.1",
    card_title: "把冲突变成一次共同练习",
    card_body: "人工复核后的方法。",
    chapters: [{ title: "先听懂情绪", body: "先复述感受。" }],
    state: "APPROVED",
    reviewed_by: "actor.synthetic.reviewer",
    review_reason: "人工确认",
    source: "SANDBOX_SYNTHETIC",
    fixture_only: true,
    external_effect: false,
    fact_write: false,
  };
}
