import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { LiveExperience } from "./LiveExperience";
import { LiveDetailPage } from "./LiveDetailPage";
import { LiveServiceOfferingPage } from "./LiveServiceOfferingPage";
import {
  LIVE_STATE_COPY,
  XIAO_JU_DENG_FIXTURE,
  resolveLiveCommerceBaseUrl,
  resolveLiveReplayBaseUrl,
  resolveLiveView,
  type LiveViewState,
} from "../live/liveCatalog";

const SYNTHETIC_PLAYBACK_DTO = JSON.stringify({
  source: "synthetic",
  fixture_only: true,
  state: "LIVE",
  media_session_ref: "media.synthetic.1",
  playback_url: "http://127.0.0.1:43123/media/media.synthetic.1.mp4?token=test-only",
  control_url: "http://127.0.0.1:43123/control/media.synthetic.1",
  sha256: "synthetic-test-digest",
});

describe("Xiao Ju Deng live product surface", () => {
  it("puts expert value first and keeps technical evidence collapsed", async () => {
    render(<LiveExperience environment={{ DEV: true }} />);

    expect(screen.getByRole("heading", { name: "和专家一起，把家庭难题聊明白" })).toBeInTheDocument();
    expect(screen.getByText("小橘灯：家庭沟通中的温柔练习")).toBeInTheDocument();
    expect(screen.getByText("真实场景、清楚方法、当下就能用。")).toBeInTheDocument();
    expect(screen.getByText("直播预告", { selector: ".live-pill" })).toBeInTheDocument();
    expect(screen.getByText("往期直播", { selector: "h3" })).toBeInTheDocument();
    expect(screen.getAllByText("#家庭沟通")).toHaveLength(2);
    expect(screen.getAllByText("内容已审核")).toHaveLength(2);
    expect(screen.getAllByRole("img", { name: "合成专家形象" })).toHaveLength(2);
    expect(screen.queryByText("MEDIA_READY")).not.toBeInTheDocument();
    expect(screen.queryByText("NO_MEDIA")).not.toBeInTheDocument();

    await userEvent.setup().click(screen.getByRole("button", { name: "查看直播详情" }));

    expect(screen.getByRole("heading", { name: "一个可以马上练习的沟通方法" })).toBeInTheDocument();
    expect(screen.getByText("围绕家庭沟通中的具体场景，练习可核对、可暂停的表达方式。")).toBeInTheDocument();
    expect(screen.getByText("视频服务暂未连接，请稍后刷新或返回直播首页。")).toBeInTheDocument();
    expect(screen.getByText("收藏与回看将在获得明确授权后开放。")).toBeInTheDocument();
    const diagnostics = screen.getByText("开发诊断信息").closest("details");
    expect(diagnostics).not.toHaveAttribute("open");
    expect(screen.getByText("review:H-LIVE-01")).toBeInTheDocument();
    expect(screen.getByText("H-LIVE-01.v1")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /收藏|回看/ })).not.toBeInTheDocument();
    expect(XIAO_JU_DENG_FIXTURE.source).toBe("SANDBOX_SYNTHETIC");
    expect(XIAO_JU_DENG_FIXTURE.fixture_only).toBe(true);
    expect(XIAO_JU_DENG_FIXTURE.capabilities).toEqual({ favorite: "LOCKED", replay: "LOCKED" });
  });

  it("keeps production fixture access fail-closed", () => {
    expect(resolveLiveView({ DEV: false })).toEqual({ state: "backend-missing", record: null });
    render(<LiveExperience environment={{ DEV: false }} />);
    expect(screen.getByText("后端未接入")).toBeInTheDocument();
    expect(screen.queryByText(XIAO_JU_DENG_FIXTURE.title)).not.toBeInTheDocument();
  });

  it("renders a non-autoplay video only for a local synthetic playback DTO", async () => {
    const { container } = render(
      <LiveExperience environment={{ DEV: true, VITE_MEDIA_PLAYBACK_DTO: SYNTHETIC_PLAYBACK_DTO }} />,
    );
    await userEvent.setup().click(screen.getByRole("button", { name: "进入直播间" }));

    const video = container.querySelector("video");
    expect(video).not.toBeNull();
    expect(video?.getAttribute("aria-label")).toBe("小橘灯合成视频播放区域");
    expect(video?.getAttribute("src")).toContain("http://127.0.0.1:43123/");
    expect(video?.hasAttribute("controls")).toBe(true);
    expect(video?.hasAttribute("playsinline")).toBe(true);
    expect(video?.getAttribute("poster")).toMatch(/^data:image\/svg\+xml,/);
    expect(video?.getAttribute("preload")).toBe("none");
    expect(video?.hasAttribute("autoplay")).toBe(false);
    expect(screen.getByText("可以播放")).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "直播间信息" })).toBeInTheDocument();
    expect(screen.getByText("直播讨论")).toBeInTheDocument();
    expect(screen.getByText("互动服务暂不可用")).toBeInTheDocument();
    expect(screen.queryByText("LIVE")).not.toBeInTheDocument();
  });

  it("submits an adult question for human review through the local sandbox", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          question_ref: "question.test",
          session_ref: "media.synthetic.1",
          text: "怎样先听懂再回应？",
          status: "PENDING",
          source: "SANDBOX_SYNTHETIC",
          fixture_only: true,
        }),
      });
    vi.stubGlobal("fetch", fetchMock);
    render(
      <LiveExperience
        environment={{
          DEV: true,
          VITE_MEDIA_PLAYBACK_DTO: SYNTHETIC_PLAYBACK_DTO,
          VITE_LIVE_INTERACTION_BASE_URL: "http://127.0.0.1:55200",
        }}
      />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "进入直播间" }));
    await user.type(screen.getByRole("textbox", { name: "向专家提问" }), "怎样先听懂再回应？");
    await user.click(screen.getByRole("button", { name: "提交" }));
    expect(await screen.findByText("问题已提交，等待人工审核")).toBeInTheDocument();
    expect(screen.getByText("等待人工审核", { selector: "em" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    vi.unstubAllGlobals();
  });

  it("rejects a non-local playback URL and keeps the surface fail-closed", () => {
    const externalDto = SYNTHETIC_PLAYBACK_DTO.replace("http://127.0.0.1:43123", "https://unverified.example");
    const view = resolveLiveView({ DEV: true, VITE_MEDIA_PLAYBACK_DTO: externalDto });
    expect(view.record?.playback).toBeUndefined();
    expect(view.record?.playback_state).toBe("WAITING_AUTHORIZATION");
  });

  it("lets an adult recover from a simulated disconnect without leaking tokens", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ state: "DISCONNECTED" }) })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          state: "LIVE",
          playback_url: "http://127.0.0.1:43123/media/media.synthetic.1.mp4?token=recovered",
        }),
      });
    vi.stubGlobal("fetch", fetchMock);
    const { container } = render(
      <LiveExperience environment={{ DEV: true, VITE_MEDIA_PLAYBACK_DTO: SYNTHETIC_PLAYBACK_DTO }} />,
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "进入直播间" }));
    await user.click(screen.getByText("连接演练工具"));
    await user.click(screen.getByRole("button", { name: "中断连接" }));
    expect(await screen.findByText("直播连接中断。")).toBeInTheDocument();
    expect(container.querySelector("video")).toBeNull();
    await user.click(screen.getByRole("button", { name: "重新连接" }));
    expect(await screen.findByText("可以播放")).toBeInTheDocument();
    expect(container.querySelector("video")).not.toBeNull();
    expect(container.textContent).not.toContain("token=recovered");
    expect(fetchMock).toHaveBeenCalledTimes(2);
    vi.unstubAllGlobals();
  });

  it.each([
    ["DISCONNECTED", "直播连接中断。", false],
    ["RESTARTED", "连接已经恢复，可以继续观看。", true],
    ["STOPPED", "本场直播已经停止。", false],
    ["REVOKED", "观看权限已经撤回。", false],
    ["FAILED", "视频暂时不可用。", false],
  ] as const)("renders the expected safe video surface for %s", (state, message, showsVideo) => {
    const record = {
      ...XIAO_JU_DENG_FIXTURE,
      playback_state: state,
      playback: { ...JSON.parse(SYNTHETIC_PLAYBACK_DTO), state },
    } as typeof XIAO_JU_DENG_FIXTURE;
    const { container } = render(<LiveDetailPage record={record} onBack={() => undefined} />);
    expect(Boolean(container.querySelector("video"))).toBe(showsVideo);
    expect(screen.getByText(message)).toBeInTheDocument();
  });

  it("offers an adult-only link to a separate service page after a session stops", () => {
    const record = {
      ...XIAO_JU_DENG_FIXTURE,
      playback_state: "STOPPED",
      playback: { ...JSON.parse(SYNTHETIC_PLAYBACK_DTO), state: "STOPPED" },
    } as typeof XIAO_JU_DENG_FIXTURE;
    render(<LiveDetailPage record={record} onBack={() => undefined} />);
    expect(screen.getByText("仅限成人")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "需要继续支持？先了解专家服务方式" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看服务方案" })).toHaveAttribute("href", "#live-service");
  });

  it("uses adult-facing language and keeps commerce contracts separate", () => {
    render(<LiveServiceOfferingPage />);
    expect(screen.getByRole("heading", { level: 2, name: "支持这场内容" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "会员权益" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "付费内容" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "预约30分钟真人咨询" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "了解平台积分" })).toBeInTheDocument();
    expect(screen.getByText(/不会获得优先提问、私聊或预约权/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "暂不可预约" })).toBeDisabled();
  });

  it("keeps content support distinct and reversible on the adult hub", async () => {
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(async (_input, init) => {
        const payload = JSON.parse(String(init?.body)) as { purchase_ref: string };
        return {
          ok: true,
          json: async () => ({
            purchase_ref: payload.purchase_ref,
            track: "CONTENT_SUPPORT",
            external_effect: false,
            source: "SANDBOX_SYNTHETIC",
            fixture_only: true,
          }),
        };
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          purchase_ref: "content-support.ui.1234",
          cash: 500,
          settlement: 500,
          entitlement: "ACTIVE",
          external_effect: false,
          source: "SANDBOX_SYNTHETIC",
          fixture_only: true,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          state: "REVERSED",
          external_effect: false,
          source: "SANDBOX_SYNTHETIC",
          fixture_only: true,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          purchase_ref: "content-support.ui.1234",
          cash: 0,
          settlement: 0,
          entitlement: "REVOKED",
          external_effect: false,
          source: "SANDBOX_SYNTHETIC",
          fixture_only: true,
        }),
      });
    vi.stubGlobal("fetch", fetchMock);
    render(<LiveServiceOfferingPage commerceBaseUrl="http://127.0.0.1:55400" />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "支持这场内容（演示）" }));
    expect(await screen.findByText("演示记录已创建，没有真实扣款。")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "撤销演示记录" }));
    expect(await screen.findByText(/演示记录已撤销/)).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("activates and reverses an independent sandbox membership contract", async () => {
    localStorage.clear();
    let membershipPurchaseRef = "";
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(async (_input, init) => {
        const payload = JSON.parse(String(init?.body)) as {
          purchase_ref: string;
          track: string;
          subject_ref: string;
          idempotency_key: string;
        };
        membershipPurchaseRef = payload.purchase_ref;
        expect(payload.track).toBe("MEMBERSHIP");
        expect(payload.subject_ref).toBe("membership.synthetic.orange-light");
        expect(payload.idempotency_key).toMatch(/^membership-idempotency\.ui\./);
        expect(payload.purchase_ref).toMatch(/^membership\.ui\./);
        expect(payload.purchase_ref).not.toMatch(/^content-support\./);
        return {
          ok: true,
          json: async () => ({
            purchase_ref: payload.purchase_ref,
            track: "MEMBERSHIP",
            external_effect: false,
            source: "SANDBOX_SYNTHETIC",
            fixture_only: true,
          }),
        };
      })
      .mockImplementationOnce(async (input) => {
        expect(String(input)).toContain(encodeURIComponent(membershipPurchaseRef));
        return {
          ok: true,
          json: async () => ({
            purchase_ref: membershipPurchaseRef,
            cash: 3000,
            settlement: 3000,
            entitlement: "ACTIVE",
            external_effect: false,
            source: "SANDBOX_SYNTHETIC",
            fixture_only: true,
          }),
        };
      })
      .mockImplementationOnce(async (input, init) => {
        expect(String(input)).toContain(`${encodeURIComponent(membershipPurchaseRef)}/reversals`);
        const payload = JSON.parse(String(init?.body)) as { reversal_ref: string };
        expect(payload.reversal_ref).toMatch(/^membership-reversal\.ui\./);
        return {
          ok: true,
          json: async () => ({
            state: "REVERSED",
            external_effect: false,
            source: "SANDBOX_SYNTHETIC",
            fixture_only: true,
          }),
        };
      })
      .mockImplementationOnce(async (input) => {
        expect(String(input)).toContain(encodeURIComponent(membershipPurchaseRef));
        return {
          ok: true,
          json: async () => ({
            purchase_ref: membershipPurchaseRef,
            cash: 0,
            settlement: 0,
            entitlement: "REVOKED",
            external_effect: false,
            source: "SANDBOX_SYNTHETIC",
            fixture_only: true,
          }),
        };
      });
    vi.stubGlobal("fetch", fetchMock);
    render(<LiveServiceOfferingPage commerceBaseUrl="http://127.0.0.1:55400" />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "开通小橘灯会员（演示）" }));
    expect(await screen.findByText("会员权益：已开通（演示）")).toBeInTheDocument();
    expect(localStorage.getItem("xiaojudeng.sandbox.membership.purchase_ref")).toBe(membershipPurchaseRef);
    expect(screen.getByText(/不会影响观看、提问或回看/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "撤销会员演示记录" }));
    expect(await screen.findByText("会员权益：已撤销（演示）")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(4);
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("restores membership from the server balance using only the stored purchase reference", async () => {
    localStorage.setItem("xiaojudeng.sandbox.membership.purchase_ref", "membership.ui.saved");
    const fetchMock = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        purchase_ref: "membership.ui.saved",
        cash: 3000,
        settlement: 3000,
        entitlement: "ACTIVE",
        external_effect: false,
        source: "SANDBOX_SYNTHETIC",
        fixture_only: true,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<LiveServiceOfferingPage commerceBaseUrl="http://127.0.0.1:55400" />);

    expect(await screen.findByText("会员权益：已开通（演示）")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:55400/sandbox/live-commerce/purchases/membership.ui.saved/balances",
      { headers: expect.any(Object) },
    );
    expect(localStorage).toHaveLength(1);
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  it.each([
    { source: "UNVERIFIED", fixture_only: true, external_effect: false },
    { source: "SANDBOX_SYNTHETIC", fixture_only: false, external_effect: false },
    { source: "SANDBOX_SYNTHETIC", fixture_only: true, external_effect: true },
  ])("rejects unsafe membership evidence: $source/$fixture_only/$external_effect", async (evidence) => {
    localStorage.clear();
    const fetchMock = vi.fn().mockImplementationOnce(async (_input, init) => {
      const payload = JSON.parse(String(init?.body)) as { purchase_ref: string };
      return {
        ok: true,
        json: async () => ({
          purchase_ref: payload.purchase_ref,
          track: "MEMBERSHIP",
          ...evidence,
        }),
      };
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<LiveServiceOfferingPage commerceBaseUrl="http://127.0.0.1:55400" />);

    await userEvent.setup().click(screen.getByRole("button", { name: "开通小橘灯会员（演示）" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "会员演示服务不可用，没有产生扣款或权益变化。",
    );
    expect(localStorage.getItem("xiaojudeng.sandbox.membership.purchase_ref")).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });

  it("purchases an adult replay entitlement, plays it, and removes it with a lineage receipt", async () => {
    localStorage.removeItem("xiaojudeng.sandbox.media_entitlement.purchase_ref");
    const record = {
      ...XIAO_JU_DENG_FIXTURE,
      playback_state: "STOPPED",
      playback: { ...JSON.parse(SYNTHETIC_PLAYBACK_DTO), state: "STOPPED" },
    } as typeof XIAO_JU_DENG_FIXTURE;
    let mediaPurchaseRef = "";
    const fetchMock = vi
      .fn()
      .mockImplementationOnce(async (_input: RequestInfo | URL, init?: RequestInit) => {
        const payload = JSON.parse(String(init?.body)) as { purchase_ref: string };
        mediaPurchaseRef = payload.purchase_ref;
        return {
        ok: true,
        json: async () => ({
          purchase_ref: mediaPurchaseRef,
          track: "MEDIA_ENTITLEMENT",
          source: "SANDBOX_SYNTHETIC",
          fixture_only: true,
          external_effect: false,
        }),
        };
      })
      .mockImplementationOnce(async () => ({
        ok: true,
        json: async () => ({
          purchase_ref: mediaPurchaseRef,
          cash: 1200,
          settlement: 0,
          entitlement: "ACTIVE",
          source: "SANDBOX_SYNTHETIC",
          fixture_only: true,
          external_effect: false,
        }),
      }))
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_ref: "media.synthetic.1",
          state: "AVAILABLE",
          playback_url: "http://127.0.0.1:55300/sandbox/replays/media.synthetic.1/media?capability=test",
          source: "SANDBOX_SYNTHETIC",
          fixture_only: true,
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          deletion_ref: "replay-deletion.test",
          session_ref: "media.synthetic.1",
          affected_refs: ["asset.source", "asset.transcode", "asset.transcript", "asset.chapters", "asset.cache", "asset.provider"],
          state: "DELETED",
          source: "SANDBOX_SYNTHETIC",
          fixture_only: true,
        }),
      });
    vi.stubGlobal("fetch", fetchMock);
    const { container } = render(
      <LiveDetailPage
        record={record}
        replayBaseUrl="http://127.0.0.1:55300"
        commerceBaseUrl="http://127.0.0.1:55400"
        onBack={() => undefined}
      />,
    );
    const user = userEvent.setup();
    expect(screen.getAllByText("已结束")).toHaveLength(2);
    expect(screen.getByText("本场主题")).toBeInTheDocument();
    expect(screen.queryByText("正在讲")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "解锁并播放回看（演示）" }));
    expect(await screen.findByLabelText("小橘灯合成直播回看")).toBeInTheDocument();
    const oldUrl = container.querySelector("video")?.getAttribute("src");
    expect(oldUrl).toContain("capability=test");
    await user.click(screen.getByRole("button", { name: "删除回看" }));
    expect(await screen.findByText("回看已删除")).toBeInTheDocument();
    expect(screen.getByText("6 项血缘已确认；刷新或重启后也不会恢复。")).toBeInTheDocument();
    expect(container.querySelector("video")).toBeNull();
    const purchaseBody = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body)) as {
      purchase_ref: string;
      track: string;
    };
    expect(purchaseBody.track).toBe("MEDIA_ENTITLEMENT");
    expect(localStorage.getItem("xiaojudeng.sandbox.media_entitlement.purchase_ref")).toBe(
      purchaseBody.purchase_ref,
    );
    expect(fetchMock).toHaveBeenCalledTimes(4);
    localStorage.removeItem("xiaojudeng.sandbox.media_entitlement.purchase_ref");
    vi.unstubAllGlobals();
  });

  it("restores a revoked replay entitlement from Commerce and refuses to render playback", async () => {
    localStorage.setItem(
      "xiaojudeng.sandbox.media_entitlement.purchase_ref",
      "media-entitlement.ui.revoked",
    );
    const record = {
      ...XIAO_JU_DENG_FIXTURE,
      playback_state: "STOPPED",
      playback: { ...JSON.parse(SYNTHETIC_PLAYBACK_DTO), state: "STOPPED" },
    } as typeof XIAO_JU_DENG_FIXTURE;
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        purchase_ref: "media-entitlement.ui.revoked",
        cash: 0,
        settlement: 0,
        entitlement: "REVOKED",
        source: "SANDBOX_SYNTHETIC",
        fixture_only: true,
        external_effect: false,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const { container } = render(
      <LiveDetailPage
        record={record}
        replayBaseUrl="http://127.0.0.1:55300"
        commerceBaseUrl="http://127.0.0.1:55400"
        onBack={() => undefined}
      />,
    );

    expect(await screen.findByText("回看权益已撤销")).toBeInTheDocument();
    expect(container.querySelector("video")).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
    localStorage.removeItem("xiaojudeng.sandbox.media_entitlement.purchase_ref");
  });

  it("fails closed when Commerce returns unsafe replay entitlement evidence", async () => {
    localStorage.removeItem("xiaojudeng.sandbox.media_entitlement.purchase_ref");
    const record = {
      ...XIAO_JU_DENG_FIXTURE,
      playback_state: "STOPPED",
      playback: { ...JSON.parse(SYNTHETIC_PLAYBACK_DTO), state: "STOPPED" },
    } as typeof XIAO_JU_DENG_FIXTURE;
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        purchase_ref: "media-entitlement.ui.unsafe",
        track: "MEDIA_ENTITLEMENT",
        source: "PRODUCTION",
        fixture_only: false,
        external_effect: true,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <LiveDetailPage
        record={record}
        replayBaseUrl="http://127.0.0.1:55300"
        commerceBaseUrl="http://127.0.0.1:55400"
        onBack={() => undefined}
      />,
    );
    await userEvent.setup().click(screen.getByRole("button", { name: "解锁并播放回看（演示）" }));

    expect(await screen.findByRole("button", { name: "重新解锁回看" })).toBeInTheDocument();
    expect(localStorage.getItem("xiaojudeng.sandbox.media_entitlement.purchase_ref")).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });

  it("rejects non-local replay adapters", () => {
    expect(resolveLiveReplayBaseUrl({
      DEV: true,
      VITE_LIVE_REPLAY_BASE_URL: "https://unverified.example",
    })).toBeUndefined();
  });

  it("keeps immediate gifting and points out of the live room", () => {
    const record = {
      ...XIAO_JU_DENG_FIXTURE,
      status: "LIVE",
      playback_state: "LIVE",
      playback: JSON.parse(SYNTHETIC_PLAYBACK_DTO),
    } as typeof XIAO_JU_DENG_FIXTURE;
    render(<LiveDetailPage record={record} onBack={() => undefined} />);
    expect(screen.queryByRole("button", { name: /打赏|积分|支持 5 元/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/橘灯会员/)).not.toBeInTheDocument();
  });

  it("rejects non-local commerce adapters", () => {
    expect(resolveLiveCommerceBaseUrl({
      DEV: true,
      VITE_LIVE_COMMERCE_BASE_URL: "https://unverified.example",
    })).toBeUndefined();
  });

  it("shows a useful empty result when the problem search has no match", async () => {
    render(<LiveExperience environment={{ DEV: true }} />);
    await userEvent.setup().type(
      screen.getByRole("searchbox", { name: "你想解决什么问题？" }),
      "不存在的问题",
    );
    expect(screen.getByText("没有匹配的直播")).toBeInTheDocument();
    expect(screen.getAllByText("暂时没有内容", { exact: true })).toHaveLength(3);
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

  it("does not render prohibited room, child profile, ranking, or commerce fields", async () => {
    const { container } = render(<LiveExperience environment={{ DEV: true }} />);
    await userEvent.setup().click(screen.getByRole("button", { name: "查看直播详情" }));
    const text = container.textContent?.toLowerCase() ?? "";
    for (const prohibited of ["room", "token", "画像", "排序", "分数", "购买", "预约"]) {
      expect(text).not.toContain(prohibited);
    }
    expect(container.querySelector("video")).toBeNull();
    expect(container.querySelector("[src]")).toBeNull();
  });
});
