import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LiveSessionControlConsole } from "./LiveSessionControlConsole";

const session = (overrides: Record<string, unknown> = {}) => ({
  session_ref: "live.synthetic.console.1",
  title: "合成直播场次",
  speaker: "合成专家",
  status: "SCHEDULED",
  approval_status: "DRAFT",
  version: "live-session.v1",
  source: "SANDBOX_SYNTHETIC",
  fixture_only: true,
  external_effect: false,
  audit_mode: "SANDBOX_RECEIPT_ONLY",
  ...overrides,
});

afterEach(() => vi.unstubAllGlobals());

describe("LiveSessionControlConsole", () => {
  it("runs creator, human review, and operator transitions", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => [] })
      .mockResolvedValueOnce({ ok: true, json: async () => session() })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => session({ approval_status: "APPROVED", version: "live-session.v2" }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => session({
          approval_status: "APPROVED",
          status: "LIVE",
          version: "live-session.v3",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => session({
          approval_status: "APPROVED",
          status: "WITHDRAWN",
          version: "live-session.v4",
        }),
      });
    vi.stubGlobal("fetch", fetchMock);
    installMediaDevices();
    installAutoWebRtc();
    render(<LiveSessionControlConsole controlBaseUrl="http://127.0.0.1:55300" />);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "创建新的演示场次" }));
    expect(await screen.findByText("场次草稿已创建，等待人工内容审核。")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "人工审核通过" }));
    expect(await screen.findByText("人工审核完成，可以由运营开播。")).toBeInTheDocument();
    const startButton = screen.getByRole("button", { name: "开始直播" });
    expect(startButton).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "检查摄像头和麦克风" }));
    expect(await screen.findByText("摄像头和麦克风已就绪，可以开播。")).toBeInTheDocument();
    expect(await screen.findByText("WebRTC 低延迟通道已建立。")).toBeInTheDocument();
    expect(startButton).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "开始直播" }));
    expect(await screen.findByText("直播已开始，符合范围的家庭可以发现。")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "人工停止直播" }));
    expect(await screen.findByText("直播已人工停止，家庭入口已撤回。")).toBeInTheDocument();
    expect(screen.getByText("WebRTC 通道已停止。")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(5);
  });

  it("fails closed for missing and unsafe control providers", async () => {
    const { rerender } = render(<LiveSessionControlConsole />);
    expect(screen.getByText("Control Plane 暂未连接。")).toBeInTheDocument();

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => [session({ source: "PRODUCTION", fixture_only: false })],
    }));
    rerender(<LiveSessionControlConsole controlBaseUrl="http://127.0.0.1:55300" />);
    expect(await screen.findByText("场次控制面不可用，所有操作已停止。")).toBeInTheDocument();
  });
});

function installMediaDevices() {
  const videoTrack = fakeTrack("video", "Camera");
  const audioTrack = fakeTrack("audio", "Microphone");
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      enumerateDevices: vi.fn().mockResolvedValue([]),
      getUserMedia: vi.fn().mockResolvedValue({
        getAudioTracks: () => [audioTrack],
        getTracks: () => [videoTrack, audioTrack],
        getVideoTracks: () => [videoTrack],
      }),
    },
  });
}

function fakeTrack(kind: "audio" | "video", label: string) {
  return {
    addEventListener: vi.fn(),
    kind,
    label,
    readyState: "live",
    stop: vi.fn(),
  };
}

function installAutoWebRtc() {
  class AutoPeerConnection {
    static instances: AutoPeerConnection[] = [];
    connectionState: RTCPeerConnectionState = "new";
    localDescription: RTCSessionDescription | null = null;
    remoteDescription: RTCSessionDescription | null = null;
    onconnectionstatechange: ((event: Event) => void) | null = null;
    onicecandidate: ((event: RTCPeerConnectionIceEvent) => void) | null = null;
    ontrack: ((event: RTCTrackEvent) => void) | null = null;
    tracks: MediaStreamTrack[] = [];
    stream: MediaStream | null = null;
    addIceCandidate = vi.fn().mockResolvedValue(undefined);
    close = vi.fn(() => {
      this.connectionState = "closed";
    });
    createAnswer = vi.fn().mockResolvedValue({ type: "answer", sdp: "answer" });
    createOffer = vi.fn().mockResolvedValue({ type: "offer", sdp: "offer" });
    setLocalDescription = vi.fn(async (description: RTCSessionDescriptionInit) => {
      this.localDescription = description as RTCSessionDescription;
    });
    setRemoteDescription = vi.fn(async (description: RTCSessionDescriptionInit) => {
      this.remoteDescription = description as RTCSessionDescription;
      if (description.type !== "answer") return;
      const [sender, receiver] = AutoPeerConnection.instances;
      if (!sender?.stream || !receiver) return;
      sender.connectionState = "connected";
      receiver.connectionState = "connected";
      receiver.onconnectionstatechange?.(new Event("connectionstatechange"));
      sender.stream.getTracks().forEach((track) => {
        receiver.ontrack?.(
          { streams: [sender.stream as MediaStream], track } as unknown as RTCTrackEvent,
        );
      });
    });

    constructor() {
      AutoPeerConnection.instances.push(this);
    }

    addTrack(track: MediaStreamTrack, stream: MediaStream) {
      this.tracks.push(track);
      this.stream = stream;
      return {} as RTCRtpSender;
    }
  }

  vi.stubGlobal("RTCPeerConnection", AutoPeerConnection);
}
