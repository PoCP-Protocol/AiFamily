import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import App from "./App";
import { createFakeExperienceApiClient } from "./api/fakeClient";

async function fillAndSubmit() {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("你的表达"), "孩子最近不愿意写作业，我们总在争吵。 ");
  await user.click(screen.getByRole("checkbox"));
  await user.click(screen.getByRole("button", { name: "生成理解草案" }));
  return user;
}

describe("Experience Studio", () => {
  it("blocks missing consent before calling the client", async () => {
    const client = createFakeExperienceApiClient();
    const spy = vi.spyOn(client, "createDraft");
    const user = userEvent.setup();
    render(<App client={client} />);
    await user.type(screen.getByLabelText("你的表达"), "请先理解这次争吵。");
    await user.click(screen.getByRole("button", { name: "生成理解草案" }));
    expect(screen.getByText("提交前需要同意本次用途的数据读取。")).toBeInTheDocument();
    expect(spy).not.toHaveBeenCalled();
  });

  it("renders a DRAFT with provenance and human confirmation state", async () => {
    render(<App client={createFakeExperienceApiClient("human_review")} />);
    const user = await fillAndSubmit();
    expect(await screen.findByText("DRAFT")).toBeInTheDocument();
    expect(screen.getByText("测试夹具")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "打开体验回放" }));
    expect(await screen.findByText("这次体验发生了什么")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "有帮助" }));
    expect(await screen.findByText("已记录“有帮助”的反馈。")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "请求人工顾问" }));
    expect(await screen.findByText("等待人工确认")).toBeInTheDocument();
  });

  it("shows provider refusal without pretending success", async () => {
    render(<App client={createFakeExperienceApiClient("provider_not_admitted")} />);
    await fillAndSubmit();
    expect(await screen.findByText("当前模型尚未完成家庭数据准入。")).toBeInTheDocument();
    expect(screen.queryByText("DRAFT")).not.toBeInTheDocument();
  });

  it("offers same-request retry after timeout", async () => {
    render(<App client={createFakeExperienceApiClient("timeout_then_retry")} />);
    await fillAndSubmit();
    expect(await screen.findByText("模型响应超时")).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "使用同一请求重试" }));
    expect(await screen.findByText("DRAFT")).toBeInTheDocument();
  });

  it("shows deleted state and removes the draft", async () => {
    render(<App client={createFakeExperienceApiClient()} />);
    await fillAndSubmit();
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "删除这次体验及媒体引用" }));
    expect(await screen.findByText("内容已删除")).toBeInTheDocument();
    expect(screen.queryByText("DRAFT")).not.toBeInTheDocument();
  });

  it("keeps a recorded confirmation distinct from rejection", async () => {
    const client = createFakeExperienceApiClient();
    vi.spyOn(client, "decide").mockResolvedValue({
      run_id: "run-1",
      status: "recorded",
      interaction_ref: "event:confirm",
      idempotency_replayed: false,
    });
    render(<App client={client} />);
    const user = await fillAndSubmit();
    await user.click(screen.getByRole("button", { name: "确认并请求继续" }));
    expect(await screen.findByText(/已记录确认/)).toBeInTheDocument();
  });

  it("shows governed action failures instead of leaving an unhandled rejection", async () => {
    const client = createFakeExperienceApiClient();
    vi.spyOn(client, "requestHuman").mockRejectedValue(
      new Error("network failure"),
    );
    render(<App client={client} />);
    const user = await fillAndSubmit();
    await user.click(screen.getByRole("button", { name: "请求人工顾问" }));
    expect(await screen.findByText("暂时无法请求人工顾问，请稍后重试。")).toBeInTheDocument();
  });
});
