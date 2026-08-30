import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "./App";
import type { ExperienceApiClient } from "./api/client";
import { createFakeExperienceApiClient } from "./api/fakeClient";

async function openExpression() {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /我想说一件家庭小事/ }));
  return user;
}

async function fillAndSubmit() {
  const user = await openExpression();
  await user.type(screen.getByLabelText("写给自己的话"), "孩子最近不愿意写作业，我们总在争吵。 ");
  await user.click(screen.getByRole("checkbox"));
  await user.click(screen.getByRole("button", { name: "看看我们听到了什么" }));
  return user;
}

describe("家庭支持旅程", () => {
  it("shows a loading state while the support card is being prepared", async () => {
    const pendingClient = { createDraft: () => new Promise(() => undefined) } as unknown as ExperienceApiClient;
    render(<App client={pendingClient} />);
    const user = await openExpression();
    await user.type(screen.getByLabelText("写给自己的话"), "我们昨晚又因为小事吵起来了。");
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "看看我们听到了什么" }));
    expect(screen.getByText("正在整理你说的事")).toBeInTheDocument();
  });

  it("starts from the home and blocks missing consent in human language", async () => {
    const client = createFakeExperienceApiClient();
    const spy = vi.spyOn(client, "createDraft");
    render(<App client={client} />);
    const user = await openExpression();
    await user.type(screen.getByLabelText("写给自己的话"), "请先理解这次争吵。");
    await user.click(screen.getByRole("button", { name: "看看我们听到了什么" }));
    expect(screen.getByText("请先确认这次内容只用于整理你的表达。")).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it("walks from expression to support card and today's small step", async () => {
    render(<App client={createFakeExperienceApiClient("human_review")} />);
    const user = await fillAndSubmit();
    expect(await screen.findByRole("heading", { name: "我们先把这件事放在这里" })).toBeInTheDocument();
    expect(screen.getByText("你刚才说的是")).toBeInTheDocument();
    expect(screen.getByText("我们目前听到的")).toBeInTheDocument();
    expect(screen.getByText("还不确定的地方")).toBeInTheDocument();
    expect(screen.getByText("今晚可以试的一小步")).toBeInTheDocument();
    expect(screen.queryByText("DRAFT")).not.toBeInTheDocument();
    expect(screen.queryByText("provenance")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "今晚先试这一步" }));
    expect(screen.getByRole("heading", { name: "不用一次解决全部。" })).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "我今晚想先试这一步" }));
    expect(screen.getByText("已记下。明天可以从这里继续，不需要重新解释一遍。")).toBeInTheDocument();
  });

  it("shows provider refusal without pretending success", async () => {
    render(<App client={createFakeExperienceApiClient("provider_not_admitted")} />);
    await fillAndSubmit();
    expect(await screen.findByText("现在还没准备好为这段内容提供支持，请稍后再试。")).toBeInTheDocument();
    expect(screen.queryByText("我们先把这件事放在这里")).not.toBeInTheDocument();
  });

  it("offers same-request retry after a timeout", async () => {
    render(<App client={createFakeExperienceApiClient("timeout_then_retry")} />);
    await fillAndSubmit();
    expect(await screen.findByText("连接有点慢")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "再试一次" }));
    expect(await screen.findByRole("heading", { name: "我们先把这件事放在这里" })).toBeInTheDocument();
  });

  it("shows an assessment entry that uses the same support result", async () => {
    render(<App client={createFakeExperienceApiClient()} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /我想做一次小测评/ }));
    await user.click(screen.getByRole("button", { name: "沟通总是绕回争吵" }));
    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "看看我们听到了什么" }));
    expect(await screen.findByRole("heading", { name: "我们先把这件事放在这里" })).toBeInTheDocument();
  });

  it("keeps exit and delete recovery available", async () => {
    render(<App client={createFakeExperienceApiClient()} />);
    const user = await fillAndSubmit();
    await user.click(screen.getByText("更多选择"));
    await user.click(screen.getByRole("button", { name: "删除这次体验" }));
    expect(await screen.findByText("这次内容已删除")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重新开始" }));
    expect(screen.getByRole("heading", { name: "不用说得很完整。" })).toBeInTheDocument();
  });
});
