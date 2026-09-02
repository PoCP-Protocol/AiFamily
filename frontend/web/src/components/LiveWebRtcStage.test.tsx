import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LiveWebRtcStage } from "./LiveWebRtcStage";

type FakeTrack = MediaStreamTrack & { stop: ReturnType<typeof vi.fn> };

class FakePeerConnection {
  static instances: FakePeerConnection[] = [];
  static rejectOffer = false;

  connectionState: RTCPeerConnectionState = "new";
  localDescription: RTCSessionDescription | null = null;
  remoteDescription: RTCSessionDescription | null = null;
  onconnectionstatechange: ((event: Event) => void) | null = null;
  onicecandidate: ((event: RTCPeerConnectionIceEvent) => void) | null = null;
  ontrack: ((event: RTCTrackEvent) => void) | null = null;
  addIceCandidate = vi.fn().mockResolvedValue(undefined);
  addTrack = vi.fn();
  close = vi.fn(() => {
    this.connectionState = "closed";
  });
  createAnswer = vi.fn().mockResolvedValue({ type: "answer", sdp: "answer" });
  createOffer = vi.fn(async () => {
    if (FakePeerConnection.rejectOffer) throw new Error("offer failed");
    return { type: "offer", sdp: "offer" };
  });
  setLocalDescription = vi.fn(async (description: RTCSessionDescriptionInit) => {
    this.localDescription = description as RTCSessionDescription;
  });
  setRemoteDescription = vi.fn(async (description: RTCSessionDescriptionInit) => {
    this.remoteDescription = description as RTCSessionDescription;
  });

  constructor() {
    FakePeerConnection.instances.push(this);
  }

  connect(stream: MediaStream) {
    this.connectionState = "connected";
    this.onconnectionstatechange?.(new Event("connectionstatechange"));
    stream.getTracks().forEach((track) => {
      this.ontrack?.({ streams: [stream], track } as unknown as RTCTrackEvent);
    });
  }
}

beforeEach(() => {
  FakePeerConnection.instances = [];
  FakePeerConnection.rejectOffer = false;
  vi.stubGlobal("RTCPeerConnection", FakePeerConnection);
});

afterEach(() => vi.unstubAllGlobals());

describe("LiveWebRtcStage", () => {
  it("sends a source stream to an independent receiver video and closes both peers", async () => {
    const sourceStream = fakeStream(fakeTrack("video"), fakeTrack("audio"));
    const remoteVideo = fakeTrack("video");
    const remoteAudio = fakeTrack("audio");
    const remoteStream = fakeStream(remoteVideo, remoteAudio);
    const onReady = vi.fn();
    const { unmount } = render(
      <LiveWebRtcStage sourceStream={sourceStream} onReadyChange={onReady} />,
    );

    expect(screen.getByText("WebRTC 通道连接中…")).toBeInTheDocument();
    await waitFor(() => expect(FakePeerConnection.instances).toHaveLength(2));
    const [sender, receiver] = FakePeerConnection.instances;
    act(() => receiver.connect(remoteStream));

    expect(await screen.findByText("WebRTC 低延迟通道已建立。")).toBeInTheDocument();
    expect(screen.getByLabelText("本地 WebRTC 观众画面")).toHaveProperty(
      "srcObject",
      remoteStream,
    );
    expect(sender.addTrack).toHaveBeenCalledTimes(2);
    expect(onReady).toHaveBeenLastCalledWith(true);

    unmount();
    expect(sender.close).toHaveBeenCalledOnce();
    expect(receiver.close).toHaveBeenCalledOnce();
    expect(remoteVideo.stop).toHaveBeenCalledOnce();
    expect(remoteAudio.stop).toHaveBeenCalledOnce();
  });

  it("fails closed and releases peers when SDP negotiation fails", async () => {
    FakePeerConnection.rejectOffer = true;
    const onReady = vi.fn();
    render(
      <LiveWebRtcStage
        sourceStream={fakeStream(fakeTrack("video"), fakeTrack("audio"))}
        onReadyChange={onReady}
      />,
    );

    expect(await screen.findByText("WebRTC 协商失败，开播已锁定。")).toBeInTheDocument();
    expect(FakePeerConnection.instances).toHaveLength(2);
    expect(FakePeerConnection.instances[0].close).toHaveBeenCalledOnce();
    expect(FakePeerConnection.instances[1].close).toHaveBeenCalledOnce();
    expect(onReady).not.toHaveBeenCalledWith(true);
  });

  it("reports stopped without creating peers when there is no device stream", () => {
    const onReady = vi.fn();
    render(<LiveWebRtcStage sourceStream={null} onReadyChange={onReady} />);

    expect(screen.getByText("WebRTC 通道已停止。")).toBeInTheDocument();
    expect(FakePeerConnection.instances).toHaveLength(0);
    expect(onReady).toHaveBeenLastCalledWith(false);
  });
});

function fakeTrack(kind: "audio" | "video"): FakeTrack {
  return {
    kind,
    readyState: "live",
    stop: vi.fn(),
  } as unknown as FakeTrack;
}

function fakeStream(videoTrack: FakeTrack, audioTrack: FakeTrack): MediaStream {
  return {
    getTracks: () => [videoTrack, audioTrack],
  } as unknown as MediaStream;
}
