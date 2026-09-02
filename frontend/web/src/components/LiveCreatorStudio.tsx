import { useEffect, useRef, useState } from "react";

import { LiveWebRtcStage } from "./LiveWebRtcStage";

type PreviewState =
  | "idle"
  | "requesting"
  | "ready"
  | "denied"
  | "no-device"
  | "unsupported"
  | "ended"
  | "error"
  | "synthetic";

type Props = {
  onDeviceReadyChange?: (ready: boolean) => void;
  onWebRtcReadyChange?: (ready: boolean) => void;
};

type DeviceSummary = {
  camera: string;
  microphone: string;
};

const EMPTY_DEVICES: DeviceSummary = {
  camera: "尚未授权摄像头",
  microphone: "尚未授权麦克风",
};

export function LiveCreatorStudio({ onDeviceReadyChange, onWebRtcReadyChange }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const intentionalStopRef = useRef(false);
  const requestGenerationRef = useRef(0);
  const [previewState, setPreviewState] = useState<PreviewState>("idle");
  const [devices, setDevices] = useState<DeviceSummary>(EMPTY_DEVICES);
  const [activeStream, setActiveStream] = useState<MediaStream | null>(null);

  useEffect(() => {
    onDeviceReadyChange?.(previewState === "ready");
  }, [onDeviceReadyChange, previewState]);

  useEffect(() => {
    if (!videoRef.current) return;
    videoRef.current.srcObject = previewState === "ready" ? streamRef.current : null;
  }, [previewState]);

  useEffect(() => () => {
    requestGenerationRef.current += 1;
    closeStream(streamRef, intentionalStopRef);
  }, []);

  return (
    <section className="live-ops-card live-creator-studio" aria-labelledby="creator-studio-heading">
      <div>
        <span>主播设备检查</span>
        <strong id="creator-studio-heading">开播前预览</strong>
        <small>摄像头和麦克风只会在专家明确点击后请求。</small>
      </div>

      <div className="live-creator-preview" aria-live="polite">
        {previewState === "ready" ? (
          <video
            aria-label="主播本地视频预览"
            autoPlay
            muted
            playsInline
            ref={videoRef}
          />
        ) : null}
        {previewState === "synthetic" ? (
          <div className="live-creator-synthetic" role="img" aria-label="合成 DEV 主播预览">
            <strong>DEV 合成预览</strong>
            <p>SANDBOX_SYNTHETIC · fixture_only=true</p>
            <p>仅验证界面，不采集设备、不推流，也不会解锁开播。</p>
          </div>
        ) : null}
        <PreviewStatus state={previewState} />
      </div>

      <dl className="live-creator-devices">
        <div>
          <dt>摄像头</dt>
          <dd>{devices.camera}</dd>
        </div>
        <div>
          <dt>麦克风</dt>
          <dd>{devices.microphone}</dd>
        </div>
      </dl>

      <div className="live-ops-actions">
        {previewState !== "ready" ? (
          <button
            disabled={previewState === "requesting"}
            type="button"
            onClick={() => void startDevicePreview()}
          >
            {previewState === "requesting" ? "正在检查设备…" : "检查摄像头和麦克风"}
          </button>
        ) : null}
        {previewState === "ready" ? (
          <button type="button" onClick={stopPreview}>停止设备预览</button>
        ) : null}
        {previewState !== "ready" && previewState !== "requesting" ? (
          <button type="button" onClick={startSyntheticPreview}>启动合成 DEV 预览</button>
        ) : null}
      </div>
      <LiveWebRtcStage sourceStream={activeStream} onReadyChange={onWebRtcReadyChange} />
    </section>
  );

  async function startDevicePreview() {
    const requestGeneration = ++requestGenerationRef.current;
    closeStream(streamRef, intentionalStopRef);
    setActiveStream(null);
    setDevices(EMPTY_DEVICES);
    setPreviewState("requesting");

    if (!navigator.mediaDevices?.getUserMedia) {
      setPreviewState("unsupported");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
        video: true,
      });
      if (requestGenerationRef.current !== requestGeneration) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      const videoTrack = stream.getVideoTracks()[0];
      const audioTrack = stream.getAudioTracks()[0];
      if (!videoTrack || !audioTrack || videoTrack.readyState === "ended" || audioTrack.readyState === "ended") {
        stream.getTracks().forEach((track) => track.stop());
        setPreviewState("no-device");
        return;
      }

      intentionalStopRef.current = false;
      streamRef.current = stream;
      const handleTrackEnded = () => {
        if (intentionalStopRef.current) return;
        closeStream(streamRef, intentionalStopRef);
        setActiveStream(null);
        setPreviewState("ended");
      };
      stream.getTracks().forEach((track) => track.addEventListener("ended", handleTrackEnded));
      setDevices(await describeDevices(videoTrack, audioTrack));
      setActiveStream(stream);
      setPreviewState("ready");
    } catch (error) {
      setPreviewState(classifyMediaError(error));
    }
  }

  function stopPreview() {
    requestGenerationRef.current += 1;
    closeStream(streamRef, intentionalStopRef);
    setActiveStream(null);
    if (videoRef.current) videoRef.current.srcObject = null;
    setDevices(EMPTY_DEVICES);
    setPreviewState("idle");
  }

  function startSyntheticPreview() {
    requestGenerationRef.current += 1;
    closeStream(streamRef, intentionalStopRef);
    setActiveStream(null);
    setDevices({
      camera: "合成画面（非设备）",
      microphone: "合成音轨（非设备）",
    });
    setPreviewState("synthetic");
  }
}

function PreviewStatus({ state }: { state: PreviewState }) {
  const messages: Record<PreviewState, string> = {
    idle: "设备尚未检查，开播已锁定。",
    requesting: "等待浏览器设备授权…",
    ready: "摄像头和麦克风已就绪，可以开播。",
    denied: "设备权限被拒绝，请在浏览器设置中允许后重试。",
    "no-device": "未找到可用的摄像头和麦克风，开播已锁定。",
    unsupported: "当前浏览器不支持设备预览，开播已锁定。",
    ended: "设备轨道已结束，开播已锁定。",
    error: "设备检查失败，开播已锁定。",
    synthetic: "当前是合成 DEV 预览，不是真实设备或真实推流。",
  };
  return <p role="status">{messages[state]}</p>;
}

async function describeDevices(
  videoTrack: MediaStreamTrack,
  audioTrack: MediaStreamTrack,
): Promise<DeviceSummary> {
  let enumerated: MediaDeviceInfo[] = [];
  try {
    enumerated = await navigator.mediaDevices.enumerateDevices();
  } catch {
    // Live tracks are authoritative for this local check; enumeration is display-only.
  }
  const camera = enumerated.find((device) => device.kind === "videoinput");
  const microphone = enumerated.find((device) => device.kind === "audioinput");
  return {
    camera: camera?.label || videoTrack.label || "已授权摄像头",
    microphone: microphone?.label || audioTrack.label || "已授权麦克风",
  };
}

function classifyMediaError(error: unknown): PreviewState {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError" || error.name === "SecurityError") return "denied";
    if (error.name === "NotFoundError" || error.name === "DevicesNotFoundError") return "no-device";
  }
  return "error";
}

function closeStream(
  streamRef: { current: MediaStream | null },
  intentionalStopRef: { current: boolean },
) {
  intentionalStopRef.current = true;
  streamRef.current?.getTracks().forEach((track) => track.stop());
  streamRef.current = null;
}
