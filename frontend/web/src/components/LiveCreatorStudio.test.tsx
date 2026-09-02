import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LiveCreatorStudio } from "./LiveCreatorStudio";

type FakeTrack = MediaStreamTrack & {
  dispatchEnded: () => void;
  stop: ReturnType<typeof vi.fn>;
};

afterEach(() => vi.unstubAllGlobals());

describe("LiveCreatorStudio", () => {
  it("requests camera and microphone only after a click and closes every track", async () => {
    const videoTrack = fakeTrack("videoinput", "Studio Camera");
    const audioTrack = fakeTrack("audioinput", "Studio Microphone");
    const stream = fakeStream(videoTrack, audioTrack);
    const getUserMedia = vi.fn().mockResolvedValue(stream);
    installMediaDevices(getUserMedia);
    const onReady = vi.fn();
    const user = userEvent.setup();

    const { unmount } = render(<LiveCreatorStudio onDeviceReadyChange={onReady} />);
    expect(getUserMedia).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "检查摄像头和麦克风" }));

    expect(getUserMedia).toHaveBeenCalledWith({ audio: true, video: true });
    expect(await screen.findByText("摄像头和麦克风已就绪，可以开播。")).toBeInTheDocument();
    expect(screen.getByText("Studio Camera")).toBeInTheDocument();
    expect(screen.getByText("Studio Microphone")).toBeInTheDocument();
    expect(screen.getByLabelText("主播本地视频预览")).toHaveProperty("srcObject", stream);
    expect(onReady).toHaveBeenLastCalledWith(true);

    await user.click(screen.getByRole("button", { name: "停止设备预览" }));
    expect(videoTrack.stop).toHaveBeenCalledOnce();
    expect(audioTrack.stop).toHaveBeenCalledOnce();
    expect(onReady).toHaveBeenLastCalledWith(false);
    unmount();
  });

  it.each([
    ["NotAllowedError", "设备权限被拒绝，请在浏览器设置中允许后重试。"],
    ["NotFoundError", "未找到可用的摄像头和麦克风，开播已锁定。"],
  ])("shows the %s failure without marking devices ready", async (name, message) => {
    installMediaDevices(vi.fn().mockRejectedValue(new DOMException("blocked", name)));
    const onReady = vi.fn();
    const user = userEvent.setup();
    render(<LiveCreatorStudio onDeviceReadyChange={onReady} />);

    await user.click(screen.getByRole("button", { name: "检查摄像头和麦克风" }));
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(onReady).not.toHaveBeenCalledWith(true);
  });

  it("locks readiness and stops all tracks when either device track ends", async () => {
    const videoTrack = fakeTrack("videoinput", "Camera");
    const audioTrack = fakeTrack("audioinput", "Microphone");
    installMediaDevices(vi.fn().mockResolvedValue(fakeStream(videoTrack, audioTrack)));
    const onReady = vi.fn();
    const user = userEvent.setup();
    render(<LiveCreatorStudio onDeviceReadyChange={onReady} />);

    await user.click(screen.getByRole("button", { name: "检查摄像头和麦克风" }));
    expect(await screen.findByText("摄像头和麦克风已就绪，可以开播。")).toBeInTheDocument();
    act(() => videoTrack.dispatchEnded());

    expect(await screen.findByText("设备轨道已结束，开播已锁定。")).toBeInTheDocument();
    expect(screen.getByText("WebRTC 通道已停止。")).toBeInTheDocument();
    expect(videoTrack.stop).toHaveBeenCalledOnce();
    expect(audioTrack.stop).toHaveBeenCalledOnce();
    expect(onReady).toHaveBeenLastCalledWith(false);
  });

  it("labels a synthetic preview and never treats it as a real device check", async () => {
    const onReady = vi.fn();
    const user = userEvent.setup();
    render(<LiveCreatorStudio onDeviceReadyChange={onReady} />);

    await user.click(screen.getByRole("button", { name: "启动合成 DEV 预览" }));
    expect(screen.getByText("SANDBOX_SYNTHETIC · fixture_only=true")).toBeInTheDocument();
    expect(screen.getByText("当前是合成 DEV 预览，不是真实设备或真实推流。")).toBeInTheDocument();
    expect(screen.getByText("WebRTC 通道已停止。")).toBeInTheDocument();
    expect(onReady).not.toHaveBeenCalledWith(true);
  });
});

function installMediaDevices(getUserMedia: ReturnType<typeof vi.fn>) {
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      enumerateDevices: vi.fn().mockResolvedValue([]),
      getUserMedia,
    },
  });
}

function fakeTrack(kind: "audioinput" | "videoinput", label: string): FakeTrack {
  const listeners = new Set<() => void>();
  const track = {
    addEventListener: vi.fn((event: string, listener: () => void) => {
      if (event === "ended") listeners.add(listener);
    }),
    dispatchEnded: () => listeners.forEach((listener) => listener()),
    kind: kind === "audioinput" ? "audio" : "video",
    label,
    readyState: "live",
    stop: vi.fn(),
  };
  return track as unknown as FakeTrack;
}

function fakeStream(videoTrack: FakeTrack, audioTrack: FakeTrack): MediaStream {
  return {
    getAudioTracks: () => [audioTrack],
    getTracks: () => [videoTrack, audioTrack],
    getVideoTracks: () => [videoTrack],
  } as unknown as MediaStream;
}
