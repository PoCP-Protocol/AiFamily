import { useEffect, useRef, useState } from "react";

export type LiveWebRtcState = "connecting" | "live" | "failed" | "stopped";

type Props = {
  sourceStream: MediaStream | null;
  onReadyChange?: (ready: boolean) => void;
};

export function LiveWebRtcStage({ sourceStream, onReadyChange }: Props) {
  const viewerRef = useRef<HTMLVideoElement>(null);
  const senderRef = useRef<RTCPeerConnection | null>(null);
  const receiverRef = useRef<RTCPeerConnection | null>(null);
  const generationRef = useRef(0);
  const [remoteStream, setRemoteStream] = useState<MediaStream | null>(null);
  const [state, setState] = useState<LiveWebRtcState>("stopped");

  useEffect(() => {
    onReadyChange?.(state === "live");
  }, [onReadyChange, state]);

  useEffect(() => {
    if (!viewerRef.current) return;
    viewerRef.current.srcObject = state === "live" ? remoteStream : null;
  }, [remoteStream, state]);

  useEffect(() => {
    const generation = ++generationRef.current;
    closePeerConnections(senderRef, receiverRef);
    setRemoteStream(null);

    if (!sourceStream) {
      setState("stopped");
      return;
    }
    if (typeof RTCPeerConnection === "undefined") {
      setState("failed");
      return;
    }

    setState("connecting");
    const sender = new RTCPeerConnection({ iceServers: [] });
    const receiver = new RTCPeerConnection({ iceServers: [] });
    senderRef.current = sender;
    receiverRef.current = receiver;
    const expectedKinds = new Set(sourceStream.getTracks().map((track) => track.kind));
    const receivedKinds = new Set<string>();
    let receivedStream: MediaStream | null = null;
    let active = true;

    const fail = () => {
      if (!active || generationRef.current !== generation) return;
      closePeerConnections(senderRef, receiverRef);
      setRemoteStream(null);
      setState("failed");
    };
    const markLiveWhenReady = () => {
      const allKindsReceived = [...expectedKinds].every((kind) => receivedKinds.has(kind));
      if (
        active &&
        generationRef.current === generation &&
        receiver.connectionState === "connected" &&
        allKindsReceived &&
        receivedStream
      ) {
        setRemoteStream(receivedStream);
        setState("live");
      }
    };

    receiver.ontrack = (event) => {
      if (!active || generationRef.current !== generation) return;
      receivedStream = event.streams[0] ?? new MediaStream([event.track]);
      receivedStream.getTracks().forEach((track) => receivedKinds.add(track.kind));
      markLiveWhenReady();
    };
    const handleConnectionState = (peer: RTCPeerConnection) => {
      if (peer.connectionState === "failed" || peer.connectionState === "disconnected") {
        fail();
        return;
      }
      markLiveWhenReady();
    };
    sender.onconnectionstatechange = () => handleConnectionState(sender);
    receiver.onconnectionstatechange = () => handleConnectionState(receiver);

    const senderCandidates: RTCIceCandidate[] = [];
    const receiverCandidates: RTCIceCandidate[] = [];
    sender.onicecandidate = (event) => {
      if (!event.candidate) return;
      if (receiver.remoteDescription) {
        void receiver.addIceCandidate(event.candidate).catch(fail);
      } else {
        senderCandidates.push(event.candidate);
      }
    };
    receiver.onicecandidate = (event) => {
      if (!event.candidate) return;
      if (sender.remoteDescription) {
        void sender.addIceCandidate(event.candidate).catch(fail);
      } else {
        receiverCandidates.push(event.candidate);
      }
    };

    sourceStream.getTracks().forEach((track) => sender.addTrack(track, sourceStream));
    void negotiate(sender, receiver, senderCandidates, receiverCandidates).catch(fail);

    return () => {
      active = false;
      sender.onicecandidate = null;
      sender.onconnectionstatechange = null;
      receiver.onicecandidate = null;
      receiver.onconnectionstatechange = null;
      receiver.ontrack = null;
      receivedStream?.getTracks().forEach((track) => track.stop());
      closePeerConnections(senderRef, receiverRef);
    };
  }, [sourceStream]);

  return (
    <section className="live-creator-preview live-webrtc-stage" aria-label="本地 WebRTC 低延迟舞台">
      <div className="live-webrtc-heading">
        <span>本地 WebRTC 通道</span>
        <strong>独立观众画面</strong>
        <small>设备媒体经 sender → receiver 本地协商，不连接信令或生产网络。</small>
      </div>
      {state === "live" ? (
        <video
          aria-label="本地 WebRTC 观众画面"
          autoPlay
          muted
          playsInline
          ref={viewerRef}
        />
      ) : null}
      <p role="status">{stateMessage(state)}</p>
    </section>
  );
}

async function negotiate(
  sender: RTCPeerConnection,
  receiver: RTCPeerConnection,
  senderCandidates: RTCIceCandidate[],
  receiverCandidates: RTCIceCandidate[],
) {
  const offer = await sender.createOffer();
  await sender.setLocalDescription(offer);
  await receiver.setRemoteDescription(offer);
  await Promise.all(senderCandidates.splice(0).map((candidate) => receiver.addIceCandidate(candidate)));
  const answer = await receiver.createAnswer();
  await receiver.setLocalDescription(answer);
  await sender.setRemoteDescription(answer);
  await Promise.all(receiverCandidates.splice(0).map((candidate) => sender.addIceCandidate(candidate)));
}

function closePeerConnections(
  senderRef: { current: RTCPeerConnection | null },
  receiverRef: { current: RTCPeerConnection | null },
) {
  senderRef.current?.close();
  receiverRef.current?.close();
  senderRef.current = null;
  receiverRef.current = null;
}

function stateMessage(state: LiveWebRtcState): string {
  const messages: Record<LiveWebRtcState, string> = {
    connecting: "WebRTC 通道连接中…",
    live: "WebRTC 低延迟通道已建立。",
    failed: "WebRTC 协商失败，开播已锁定。",
    stopped: "WebRTC 通道已停止。",
  };
  return messages[state];
}
