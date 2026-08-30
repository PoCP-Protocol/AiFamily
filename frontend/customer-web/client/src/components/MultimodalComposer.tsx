/* 多模态记录器：浏览器本地采集与预检；转写和语义识别为明确标注的可用性测试模拟。 */
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import type { FamilyMomentDraft, MomentKind } from "@/lib/family-api";
import { AudioLines, Camera, Check, CheckCircle2, FileImage, ImagePlus, LoaderCircle, Mic, RotateCcw, ScanLine, ShieldAlert, Sparkles, Square, Type, Video, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

type VoiceStage = "idle" | "requesting" | "recording" | "transcribing" | "ready" | "error";
type ImageStage = "idle" | "preview" | "analyzing" | "ready" | "error";

interface ImageMeta {
  width: number;
  height: number;
  sizeMb: string;
  format: string;
  light: "光线充足" | "光线偏暗";
}

const modes: { kind: MomentKind; label: string; help: string; icon: typeof Type }[] = [
  { kind: "TEXT", label: "写一句", help: "记录此刻最真实的一句话", icon: Type },
  { kind: "AUDIO", label: "说出来", help: "用声音保留语气和停顿", icon: Mic },
  { kind: "IMAGE", label: "拍下来", help: "上传一张家庭时刻", icon: ImagePlus },
  { kind: "VIDEO", label: "录片段", help: "最多 30 秒的短视频", icon: Video },
];

const simulatedTags = ["共同活动", "室内场景", "可能包含未成年人"];

export function MultimodalComposer({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [kind, setKind] = useState<MomentKind>("TEXT");
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<string | null>(null);
  const [voiceStage, setVoiceStage] = useState<VoiceStage>("idle");
  const [imageStage, setImageStage] = useState<ImageStage>("idle");
  const [seconds, setSeconds] = useState(0);
  const [voiceLevel, setVoiceLevel] = useState(0);
  const [scanProgress, setScanProgress] = useState(0);
  const [imageMeta, setImageMeta] = useState<ImageMeta | null>(null);
  const [activeTags, setActiveTags] = useState(simulatedTags);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const timersRef = useRef<number[]>([]);

  const clearTimers = () => {
    timersRef.current.forEach((timer) => window.clearTimeout(timer));
    timersRef.current = [];
  };

  const stopAudioMonitor = () => {
    if (animationFrameRef.current !== null) cancelAnimationFrame(animationFrameRef.current);
    animationFrameRef.current = null;
    audioContextRef.current?.close().catch(() => undefined);
    audioContextRef.current = null;
    setVoiceLevel(0);
  };

  const stopStream = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    stopAudioMonitor();
  };

  const resetCapture = () => {
    clearTimers();
    if (recorderRef.current?.state === "recording") recorderRef.current.stop();
    stopStream();
    if (preview) URL.revokeObjectURL(preview);
    setPreview(null);
    setText("");
    setSeconds(0);
    setVoiceStage("idle");
    setImageStage("idle");
    setScanProgress(0);
    setImageMeta(null);
    setActiveTags(simulatedTags);
  };

  useEffect(() => {
    if (voiceStage !== "recording") return;
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, [voiceStage]);

  useEffect(() => () => {
    clearTimers();
    stopStream();
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  const monitorAudio = (stream: MediaStream) => {
    const audioContext = new AudioContext();
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    audioContext.createMediaStreamSource(stream).connect(analyser);
    audioContextRef.current = audioContext;
    const data = new Uint8Array(analyser.frequencyBinCount);
    const sample = () => {
      analyser.getByteFrequencyData(data);
      const average = data.reduce((total, value) => total + value, 0) / data.length;
      setVoiceLevel(Math.min(1, average / 72));
      animationFrameRef.current = requestAnimationFrame(sample);
    };
    sample();
  };

  const toggleRecording = async () => {
    if (voiceStage === "recording") {
      recorderRef.current?.stop();
      return;
    }
    setVoiceStage("requesting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => chunksRef.current.push(event.data);
      recorder.onstop = () => {
        const url = URL.createObjectURL(new Blob(chunksRef.current, { type: "audio/webm" }));
        setPreview((previous) => {
          if (previous) URL.revokeObjectURL(previous);
          return url;
        });
        stopStream();
        setVoiceStage("transcribing");
        const timer = window.setTimeout(() => {
          setText("今天我先听完孩子说完，再复述了他的意思。");
          setVoiceStage("ready");
        }, 1450);
        timersRef.current.push(timer);
      };
      recorderRef.current = recorder;
      setSeconds(0);
      setText("");
      setVoiceStage("recording");
      monitorAudio(stream);
      recorder.start();
    } catch {
      stopStream();
      setVoiceStage("error");
      toast.error("无法访问麦克风，请检查浏览器权限");
    }
  };

  const inspectImage = async (file: File): Promise<ImageMeta> => {
    const bitmap = await createImageBitmap(file);
    const canvas = document.createElement("canvas");
    canvas.width = 24;
    canvas.height = 24;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    context?.drawImage(bitmap, 0, 0, 24, 24);
    const pixels = context?.getImageData(0, 0, 24, 24).data;
    let brightness = 160;
    if (pixels) {
      let total = 0;
      for (let index = 0; index < pixels.length; index += 4) total += (pixels[index] + pixels[index + 1] + pixels[index + 2]) / 3;
      brightness = total / (pixels.length / 4);
    }
    const meta = {
      width: bitmap.width,
      height: bitmap.height,
      sizeMb: (file.size / 1024 / 1024).toFixed(1),
      format: file.type.replace("image/", "").toUpperCase() || "IMAGE",
      light: brightness >= 105 ? "光线充足" as const : "光线偏暗" as const,
    };
    bitmap.close();
    return meta;
  };

  const runImageFeedback = async (file: File) => {
    setImageStage("analyzing");
    setScanProgress(18);
    try {
      const meta = await inspectImage(file);
      setImageMeta(meta);
      const first = window.setTimeout(() => setScanProgress(62), 320);
      const second = window.setTimeout(() => {
        setScanProgress(100);
        setImageStage("ready");
      }, 1050);
      timersRef.current.push(first, second);
    } catch {
      setImageStage("error");
    }
  };

  const selectFile = (file?: File) => {
    if (!file) return;
    if (file.size > 15 * 1024 * 1024) {
      setImageStage("error");
      toast.error("图片过大，请选择 15MB 以内的文件");
      return;
    }
    if (preview) URL.revokeObjectURL(preview);
    const nextPreview = URL.createObjectURL(file);
    setPreview(nextPreview);
    if (kind === "IMAGE") void runImageFeedback(file);
    else setImageStage("preview");
  };

  const removeTag = (tag: string) => setActiveTags((tags) => tags.filter((item) => item !== tag));

  const saveDraft = () => {
    const draft: FamilyMomentDraft = {
      kind,
      text: text.trim() || undefined,
      localPreviewUrl: preview ?? undefined,
      durationSeconds: kind === "AUDIO" ? seconds : undefined,
      status: "LOCAL_DRAFT",
    };
    if (!draft.text && !draft.localPreviewUrl) {
      toast.error("先留下一点内容，再保存这一刻");
      return;
    }
    toast.success("已保存为本地体验草稿", { description: "模拟识别标签不会上传，也不会进入家庭事实。" });
    resetCapture();
    onOpenChange(false);
  };

  return (
    <Sheet open={open} onOpenChange={(next) => { if (!next) resetCapture(); onOpenChange(next); }}>
      <SheetContent side="bottom" className="mx-auto max-h-[94dvh] max-w-3xl overflow-y-auto rounded-t-[32px] border-[#E9D8CA] bg-[#FFF9F3] px-5 pb-8 sm:px-8">
        <SheetHeader className="pt-2 text-left">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-[#2563EB]"><span className="h-2 w-2 rounded-full bg-[#2563EB]" />多模态家庭记录</div>
          <SheetTitle className="font-story text-2xl font-bold text-[#10213E]">这一刻，你想怎么留下来？</SheetTitle>
          <SheetDescription>媒体只在浏览器本地预览；转写和语义识别反馈为可用性测试模拟。</SheetDescription>
        </SheetHeader>

        <div className="mt-5 grid grid-cols-4 gap-2">
          {modes.map((mode) => {
            const Icon = mode.icon;
            const active = kind === mode.kind;
            return (
              <button key={mode.kind} onClick={() => { resetCapture(); setKind(mode.kind); }} className={`rounded-2xl px-2 py-3 text-center ${active ? "bg-[#F28C45] text-white shadow-lg shadow-orange-200" : "bg-white text-[#10213E] shadow-sm"}`}>
                <Icon className="mx-auto mb-1.5 h-5 w-5" />
                <span className="block text-xs font-bold">{mode.label}</span>
              </button>
            );
          })}
        </div>

        <div className="mt-5 min-h-52 rounded-[26px] border border-[#EADFD3] bg-white p-4 shadow-sm">
          {kind === "TEXT" && <Textarea value={text} onChange={(event) => setText(event.target.value)} autoFocus placeholder="比如：今天我忍住了立刻给答案，先听孩子把话说完……" className="min-h-44 resize-none border-0 bg-transparent text-base shadow-none focus-visible:ring-0" />}
          {kind === "AUDIO" && <VoiceFeedback stage={voiceStage} seconds={seconds} level={voiceLevel} preview={preview} transcript={text} onTranscript={setText} onToggle={toggleRecording} />}
          {kind === "IMAGE" && (
            <ImageFeedback preview={preview} stage={imageStage} progress={scanProgress} meta={imageMeta} tags={activeTags} onRemoveTag={removeTag} onRemove={resetCapture} onSelect={selectFile} onRetry={() => { setImageStage("preview"); setScanProgress(0); toast("请重新选择图片以开始识别预检"); }} />
          )}
          {kind === "VIDEO" && (
            <div className="relative grid min-h-48 place-items-center overflow-hidden rounded-2xl bg-[#FFF9F3]">
              {preview ? <><video src={preview} controls className="h-60 w-full object-cover" /><button onClick={resetCapture} aria-label="移除视频" className="absolute right-3 top-3 rounded-full bg-[#10213E]/75 p-2 text-white"><X className="h-4 w-4" /></button></> : <MediaPicker kind="VIDEO" onSelect={selectFile} />}
            </div>
          )}
        </div>

        <div className="mt-4 flex items-start gap-2 rounded-2xl bg-[#F3F7FF] p-3 text-xs leading-5 text-[#5071AE]">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-[#2563EB]" />
          <span><strong className="text-[#1D4EAE]">体验边界：</strong>不会上传媒体，不会根据图片形成孩子或家庭结论；识别结果可删除、可修改。</span>
        </div>
        <div className="mt-5 flex items-center justify-between gap-3">
          <p className="hidden text-xs leading-5 text-slate-500 sm:block">不会生成家庭分数。AI 结果只能作为建议或草案。</p>
          <Button onClick={saveDraft} className="ml-auto h-12 rounded-full bg-[#F28C45] px-7 text-sm font-bold text-white hover:bg-[#DE7731]">保存这一刻</Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function VoiceFeedback({ stage, seconds, level, preview, transcript, onTranscript, onToggle }: { stage: VoiceStage; seconds: number; level: number; preview: string | null; transcript: string; onTranscript: (value: string) => void; onToggle: () => void }) {
  const busy = stage === "requesting" || stage === "transcribing";
  return (
    <div className="grid min-h-48 gap-4 py-2 text-center">
      <div className="mx-auto flex h-14 items-end gap-1" aria-label={stage === "recording" ? "麦克风正在接收声音" : "麦克风音量反馈"}>
        {Array.from({ length: 17 }, (_, index) => {
          const distance = Math.abs(index - 8);
          const height = stage === "recording" ? 12 + Math.max(0, 34 - distance * 3) * Math.max(.18, level) : 8 + (index % 3) * 4;
          return <span key={index} className={`w-1.5 rounded-full transition-all duration-100 ${stage === "recording" ? "bg-[#2563EB]" : "bg-[#C9D8F8]"}`} style={{ height }} />;
        })}
      </div>
      <div className="flex items-center justify-center gap-5">
        <button disabled={busy} onClick={onToggle} aria-label={stage === "recording" ? "停止录音" : "开始录音"} className={`grid h-18 w-18 place-items-center rounded-full text-white shadow-xl ${stage === "recording" ? "bg-[#2563EB] shadow-blue-200" : busy ? "bg-slate-300" : "soft-pulse bg-[#F28C45] shadow-orange-200"}`}>
          {stage === "requesting" || stage === "transcribing" ? <LoaderCircle className="h-7 w-7 animate-spin" /> : stage === "recording" ? <Square className="h-6 w-6 fill-current" /> : <Mic className="h-7 w-7" />}
        </button>
        <div className="text-left"><div className="font-score text-2xl font-extrabold text-[#10213E]">{String(Math.floor(seconds / 60)).padStart(2, "0")}:{String(seconds % 60).padStart(2, "0")}</div><p className="mt-1 text-sm text-slate-500">{stage === "requesting" ? "正在请求麦克风权限…" : stage === "recording" ? "正在倾听，再点一次完成" : stage === "transcribing" ? "正在生成模拟转写…" : stage === "ready" ? "转写完成，可以修改" : stage === "error" ? "麦克风权限不可用" : "轻点开始，说出真实感受"}</p></div>
      </div>
      {stage === "error" && <button onClick={onToggle} className="mx-auto flex items-center gap-2 text-sm font-bold text-[#2563EB]"><RotateCcw className="h-4 w-4" />重新申请权限</button>}
      {preview && <audio src={preview} controls className="mx-auto w-full max-w-md" />}
      {stage === "ready" && <div className="rounded-2xl border border-[#D8E4FF] bg-[#F3F7FF] p-4 text-left"><div className="mb-2 flex items-center justify-between gap-3"><span className="flex items-center gap-2 text-xs font-bold text-[#2563EB]"><AudioLines className="h-4 w-4" />模拟转写结果</span><span className="text-[10px] font-semibold text-[#6781B4]">未上传 · 可编辑</span></div><Textarea value={transcript} onChange={(event) => onTranscript(event.target.value)} className="min-h-20 border-0 bg-white text-sm leading-6 shadow-none" /></div>}
    </div>
  );
}

function ImageFeedback({ preview, stage, progress, meta, tags, onRemoveTag, onRemove, onSelect, onRetry }: { preview: string | null; stage: ImageStage; progress: number; meta: ImageMeta | null; tags: string[]; onRemoveTag: (tag: string) => void; onRemove: () => void; onSelect: (file?: File) => void; onRetry: () => void }) {
  if (!preview) return <div className="grid min-h-48 place-items-center rounded-2xl bg-[#FFF9F3]"><MediaPicker kind="IMAGE" onSelect={onSelect} /></div>;
  return (
    <div className="grid gap-4 md:grid-cols-[1.08fr_.92fr]">
      <div className="relative min-h-56 overflow-hidden rounded-2xl bg-[#10213E]">
        <img src={preview} alt="待分析家庭记录预览" className="h-full min-h-56 w-full object-cover" />
        {stage === "analyzing" && <><div className="absolute inset-0 bg-[#10213E]/30" /><div className="scan-beam absolute inset-x-0 h-1 bg-[#F28C45] shadow-[0_0_22px_6px_rgba(242,140,69,.55)]" /><div className="absolute inset-0 grid place-items-center"><span className="flex items-center gap-2 rounded-full bg-[#10213E]/82 px-4 py-2 text-xs font-bold text-white backdrop-blur"><ScanLine className="h-4 w-4 text-[#FFC092]" />本地预检与模拟识别 {progress}%</span></div></>}
        <button onClick={onRemove} aria-label="移除图片" className="absolute right-3 top-3 rounded-full bg-[#10213E]/75 p-2 text-white"><X className="h-4 w-4" /></button>
      </div>
      <div className="rounded-2xl bg-[#FFF9F3] p-4">
        {stage === "analyzing" && <div className="grid h-full place-items-center text-center"><LoaderCircle className="h-7 w-7 animate-spin text-[#2563EB]" /><div><strong className="text-sm">正在检查图片质量</strong><p className="mt-2 text-xs leading-5 text-slate-500">尺寸与光线在本地计算；场景标签为模拟反馈。</p></div></div>}
        {stage === "error" && <div className="grid h-full place-items-center text-center"><ShieldAlert className="h-8 w-8 text-[#D64B4B]" /><div><strong className="text-sm">图片预检未完成</strong><p className="mt-2 text-xs text-slate-500">请重新选择有效的图片文件。</p><button onClick={onRetry} className="mt-3 text-xs font-bold text-[#2563EB]">重新尝试</button></div></div>}
        {stage === "ready" && <div><div className="flex items-center gap-2 text-xs font-bold text-[#16866D]"><CheckCircle2 className="h-4 w-4" />本地预检完成</div>{meta && <div className="mt-3 grid grid-cols-2 gap-2 text-xs"><Meta label="尺寸" value={`${meta.width} × ${meta.height}`} /><Meta label="文件" value={`${meta.format} · ${meta.sizeMb}MB`} /><Meta label="方向" value={meta.width >= meta.height ? "横向" : "竖向"} /><Meta label="光线" value={meta.light} /></div>}<div className="mt-4 flex items-center gap-2 text-xs font-bold text-[#2563EB]"><Sparkles className="h-4 w-4" />模拟识别标签</div><div className="mt-2 flex flex-wrap gap-2">{tags.map((tag) => <button key={tag} onClick={() => onRemoveTag(tag)} className="flex items-center gap-1 rounded-full bg-[#EAF1FF] px-3 py-1.5 text-[11px] font-semibold text-[#1D4EAE]">{tag}<X className="h-3 w-3" /></button>)}</div><p className="mt-3 text-[11px] leading-5 text-slate-500">标签不会自动成为家庭事实，可点击删除。</p></div>}
      </div>
    </div>
  );
}

function MediaPicker({ kind, onSelect }: { kind: "IMAGE" | "VIDEO"; onSelect: (file?: File) => void }) {
  return <label className="grid cursor-pointer place-items-center gap-3 text-center text-[#10213E]"><span className="grid h-14 w-14 place-items-center rounded-2xl bg-[#FFF1E6] text-[#F28C45]">{kind === "IMAGE" ? <Camera className="h-6 w-6" /> : <Video className="h-6 w-6" />}</span><span><strong className="block">{kind === "IMAGE" ? "选择照片或打开相机" : "选择一段 30 秒内的视频"}</strong><small className="text-slate-500">浏览器端先预览，不会自动上传</small></span><input type="file" accept={kind === "IMAGE" ? "image/*" : "video/*"} capture="environment" className="sr-only" onChange={(event) => onSelect(event.target.files?.[0])} /></label>;
}

function Meta({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl bg-white p-2.5"><span className="block text-[10px] text-slate-400">{label}</span><strong className="mt-1 block truncate text-[11px] text-[#10213E]">{value}</strong></div>;
}
