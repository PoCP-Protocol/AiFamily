/* 今日行动页强化开始—暂停—继续—取消—完成—复盘状态机，并保持与后端 TaskAction 语义一致。 */
import { AchievementBurst } from "@/components/AchievementBurst";
import { CustomerShell } from "@/components/CustomerShell";
import { GrowthRing } from "@/components/GrowthRing";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Check, Clock3, Flame, Pause, Play, RotateCcw, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link } from "wouter";
import { toast } from "sonner";

type TaskState = "READY" | "IN_PROGRESS" | "PAUSED" | "COMPLETED";

export default function Today() {
  const [state, setState] = useState<TaskState>("READY");
  const [celebrateOpen, setCelebrateOpen] = useState(false);

  const startOrTogglePause = () => {
    const next: TaskState = state === "READY" || state === "PAUSED" ? "IN_PROGRESS" : "PAUSED";
    setState(next);
    toast(next === "PAUSED" ? "已暂停，回来时从这里继续" : state === "PAUSED" ? "继续刚才的行动" : "行动开始了");
  };

  const complete = () => {
    setState("COMPLETED");
    setCelebrateOpen(true);
    navigator.vibrate?.(35);
  };

  const reset = () => {
    setState("READY");
    toast("这次行动已结束", { description: "体验模式不会形成真实取消回执。" });
  };

  return (
    <CustomerShell>
      <div className="mx-auto max-w-5xl px-5 py-8 sm:px-8 lg:py-12">
        <div className="enter-rise flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
          <div>
            <Badge className="border-0 bg-[#FFF1E6] text-[#D66A27]">今天 · 只做一件事</Badge>
            <h1 className="mt-4 font-story text-4xl font-black sm:text-5xl">先听完孩子的三句话。</h1>
            <p className="mt-3 max-w-2xl leading-7 text-slate-600">不解释、不纠正、不急着给答案。只需要在他说完后，复述你听见的重点。</p>
          </div>
          <div className="shrink-0"><GrowthRing progress={state === "COMPLETED" ? 100 : 72} /></div>
        </div>

        <div className="mt-10 grid gap-5 lg:grid-cols-[1.4fr_.8fr]">
          <section className="relative overflow-hidden rounded-[34px] bg-[#10213E] p-6 text-white shadow-2xl shadow-slate-300 sm:p-9">
            <div className="absolute right-0 top-0 h-64 w-64 translate-x-1/3 -translate-y-1/3 rounded-full bg-[#2563EB]/35 blur-3xl" />
            <div className="relative">
              <div className="flex items-center justify-between gap-3">
                <Badge className="border-white/15 bg-white/10 text-white"><Clock3 className="mr-1.5 h-3.5 w-3.5" />预计 3 分钟</Badge>
                <span className="text-xs font-semibold text-[#8EB2FF]">任务 ID · task-listen-07</span>
              </div>
              <h2 className="mt-12 font-story text-3xl font-bold sm:text-4xl">把“我知道了”换成<br /><span className="text-[#FFC092]">“你的意思是……”</span></h2>
              <div className="mt-8 space-y-4 text-sm text-slate-200">
                <Step done={state !== "READY"}>找一个不被打断的三分钟</Step>
                <Step done={state === "IN_PROGRESS" || state === "PAUSED" || state === "COMPLETED"}>让孩子完整说完三句话</Step>
                <Step done={state === "COMPLETED"}>复述，而不是评价</Step>
              </div>

              {state !== "COMPLETED" ? (
                <div className={`mt-10 grid gap-3 ${state === "IN_PROGRESS" ? "sm:grid-cols-2" : ""}`}>
                  <button onClick={startOrTogglePause} className="flex h-14 w-full items-center justify-center gap-2 rounded-full bg-[#F28C45] text-sm font-bold text-white hover:bg-[#DE7731]">
                    {state === "IN_PROGRESS" ? <Pause className="h-5 w-5" /> : <Play className="h-5 w-5 fill-current" />}
                    {state === "READY" ? "开始行动" : state === "PAUSED" ? "继续行动" : "暂停一下"}
                  </button>
                  {state === "IN_PROGRESS" && <button onClick={complete} className="flex h-14 w-full items-center justify-center gap-2 rounded-full bg-[#16866D] text-sm font-bold text-white hover:bg-[#11715C]"><Check className="h-5 w-5" />完成并留下记录</button>}
                </div>
              ) : (
                <Link href="/moments" className="mt-10 flex h-14 w-full items-center justify-center gap-2 rounded-full bg-[#16866D] text-sm font-bold text-white"><Check className="h-5 w-5" />行动已完成 · 去记录这一刻</Link>
              )}
              {state !== "READY" && state !== "COMPLETED" && <button onClick={reset} className="mx-auto mt-4 flex items-center gap-2 text-xs text-slate-400"><RotateCcw className="h-3.5 w-3.5" />结束并稍后再试</button>}
            </div>
          </section>

          <aside className="space-y-5">
            <div className="rounded-[30px] bg-[#FFF1E6] p-6">
              <div className="flex items-center gap-2 text-xs font-bold text-[#D66A27]"><Flame className="h-4 w-4" />连续行动</div>
              <div className="mt-3 font-score text-5xl font-extrabold text-[#10213E]">7<span className="ml-1 text-base font-bold text-slate-500">天</span></div>
              <p className="mt-3 text-sm leading-6 text-slate-600">连续不是压力。中断后可以重新开始，不会失去已经完成的经历。</p>
            </div>
            <div className="rounded-[30px] border border-[#D8E4FF] bg-[#F3F7FF] p-6">
              <div className="flex items-center gap-2 text-xs font-bold text-[#2563EB]"><Sparkles className="h-4 w-4" />为什么是这个行动</div>
              <p className="mt-3 text-sm leading-7 text-slate-600">来自你确认过的“减少立即纠正”成长方向。它是建议，不是诊断。</p>
              <button onClick={() => toast("依据说明将在接入成长计划 API 后展示")} className="mt-4 text-sm font-bold text-[#2563EB]">查看建议依据</button>
            </div>
          </aside>
        </div>
      </div>

      <Dialog open={celebrateOpen} onOpenChange={setCelebrateOpen}>
        <DialogContent className="overflow-hidden rounded-[32px] border-0 bg-[#FFF9F3] p-0 sm:max-w-md">
          <div className="relative bg-[#16866D] px-7 pb-8 pt-10 text-center text-white">
            <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(255,255,255,.25),transparent_60%)]" />
            <div className="relative mx-auto grid h-36 w-36 place-items-center"><AchievementBurst active={celebrateOpen} /><img src="/manus-storage/aifamily-achievement-emblem_3e4238f3.png" alt="共同倾听者徽章" className="achievement-badge-pop relative h-32 w-32 object-contain" /></div>
            <p className="relative mt-2 text-xs font-bold tracking-[.18em] text-white/70">共同做到的一刻</p>
            <DialogHeader className="relative mt-2 text-center">
              <DialogTitle className="font-story text-3xl font-black text-white">今天这件小事，做到了。</DialogTitle>
              <DialogDescription className="mt-3 leading-7 text-white/75">完成不是满分，也不证明孩子发生了改变。它只忠实记录：你们一起尝试过。</DialogDescription>
            </DialogHeader>
          </div>
          <div className="grid gap-3 p-6">
            <Link href="/moments" className="flex h-12 items-center justify-center rounded-full bg-[#F28C45] text-sm font-bold text-white" onClick={() => setCelebrateOpen(false)}>用文字、声音或影像留下这一刻</Link>
            <button onClick={() => setCelebrateOpen(false)} className="h-11 text-sm font-semibold text-slate-500">先回到今天</button>
          </div>
        </DialogContent>
      </Dialog>
    </CustomerShell>
  );
}

function Step({ children, done }: { children: string; done: boolean }) {
  return <div className="flex items-center gap-3"><span className={`grid h-6 w-6 place-items-center rounded-full ${done ? "bg-[#16866D] text-white" : "border border-white/20 bg-white/5 text-white/35"}`}>{done ? <Check className="h-3.5 w-3.5" /> : "·"}</span>{children}</div>;
}
