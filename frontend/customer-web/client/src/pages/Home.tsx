/* 首页遵循一屏一意图：成长洞察、今日行动、家庭记录和成就反馈纵向推进。 */
import { AchievementBurst } from "@/components/AchievementBurst";
import { CustomerShell } from "@/components/CustomerShell";
import { Badge } from "@/components/ui/badge";
import { ArrowUp, Bookmark, Check, ChevronDown, HeartHandshake, MessageCircleMore, Play, Share2, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

export default function Home() {
  const feedRef = useRef<HTMLDivElement>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [actionStarted, setActionStarted] = useState(false);
  const [savedForTonight, setSavedForTonight] = useState(false);
  const [adopted, setAdopted] = useState(false);
  const moveNext = () => feedRef.current?.scrollBy({ top: feedRef.current.clientHeight, behavior: "smooth" });

  useEffect(() => {
    const root = feedRef.current;
    if (!root) return;
    const sections = Array.from(root.querySelectorAll<HTMLElement>("[data-feed-index]"));
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (visible) setActiveIndex(Number((visible.target as HTMLElement).dataset.feedIndex ?? 0));
    }, { root, threshold: [.45, .65, .82] });
    sections.forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, []);

  const startAction = () => {
    setActionStarted(true);
    navigator.vibrate?.(25);
    toast.success("行动已开始", { description: "计时不会给家庭打分，只帮助你留出专注的 3 分钟。" });
  };

  return (
    <CustomerShell immersive>
      <div ref={feedRef} className="feed-snap hide-scrollbar relative h-[calc(100dvh-4rem)] overflow-y-auto lg:h-dvh">
        <div className="pointer-events-none fixed right-4 top-20 z-30 flex items-center gap-2 rounded-full bg-[#10213E]/70 px-3 py-2 text-white backdrop-blur lg:right-[312px] lg:top-4">
          <span className="font-score text-xs font-extrabold">0{activeIndex + 1}</span>
          <div className="flex gap-1">{[0, 1, 2].map((index) => <span key={index} className={`h-1.5 rounded-full transition-all duration-200 ${activeIndex === index ? "w-5 bg-[#F28C45]" : "w-1.5 bg-white/45"}`} />)}</div>
          <span className="text-[10px] text-white/65">03</span>
        </div>

        <section data-feed-index="0" className="feed-panel relative min-h-full overflow-hidden bg-[#10213E] text-white">
          <img src="/manus-storage/aifamily-hero-reference_326fab45.jpg" alt="一家人在客厅共同完成搭桥小行动" className="absolute inset-0 h-full w-full object-cover object-center opacity-90" />
          <div className="absolute inset-0 bg-gradient-to-t from-[#10213E] via-[#10213E]/25 to-[#10213E]/15" />
          <div className="paper-noise absolute inset-0" />
          <div className="relative flex min-h-[calc(100dvh-4rem)] flex-col justify-end px-5 pb-10 pt-28 sm:px-9 lg:min-h-dvh lg:px-12 lg:pb-12">
            <div className="feed-focus" data-active={activeIndex === 0}>
              <Badge className="mb-4 w-fit border-white/25 bg-white/15 text-white backdrop-blur">今日家庭行动 · 3 分钟</Badge>
              <h1 className="font-story max-w-2xl text-balance text-[2.4rem] font-black leading-[1.18] tracking-tight sm:text-5xl">今天，不解决所有问题。<br /><span className="text-[#FFC092]">只把一件小事做好。</span></h1>
              <p className="mt-5 max-w-xl text-base leading-7 text-white/80">一起搭一座不会倒的小桥。孩子负责选择，你只负责问：“你想先试哪一种？”</p>
              <div className="mt-7 flex flex-wrap items-center gap-3">
                <button onClick={startAction} className={`flex h-12 items-center gap-2 rounded-full px-6 text-sm font-bold text-white shadow-xl shadow-black/20 ${actionStarted ? "bg-[#16866D]" : "bg-[#F28C45]"}`}>{actionStarted ? <Check className="h-4 w-4" /> : <Play className="h-4 w-4 fill-current" />}{actionStarted ? "行动进行中 · 进入详情" : "开始 3 分钟行动"}</button>
                <button onClick={() => { setSavedForTonight((value) => !value); toast(savedForTonight ? "已从今晚移除" : "已加入今晚"); }} className={`h-12 rounded-full border px-5 text-sm font-semibold text-white backdrop-blur ${savedForTonight ? "border-[#F28C45] bg-[#F28C45]/25" : "border-white/30 bg-white/12"}`}>{savedForTonight ? "已加入今晚" : "留到今晚"}</button>
              </div>
              <div className="mt-8 flex items-end justify-between"><div className="flex items-center gap-2 text-xs text-white/65"><Sparkles className="h-4 w-4 text-[#F28C45]" />由家庭成长计划推荐 · 可调整</div><ActionRail /></div>
            </div>
            <button onClick={moveNext} aria-label="浏览下一条" className="absolute bottom-3 left-1/2 -translate-x-1/2 text-white/70"><ChevronDown className="h-6 w-6" /></button>
          </div>
        </section>

        <section data-feed-index="1" className="feed-panel relative min-h-full overflow-hidden bg-[#F8E4D3] text-[#10213E]">
          <img src="/manus-storage/aifamily-feed-listening_6a352ec7.jpg" alt="家长与孩子在窗边进行倾听练习" className="absolute inset-0 h-full w-full object-cover object-center" />
          <div className="absolute inset-0 bg-gradient-to-t from-[#FFF1E6] via-[#FFF1E6]/35 to-transparent" />
          <div className="relative flex min-h-[calc(100dvh-4rem)] flex-col justify-end px-5 pb-12 sm:px-9 lg:min-h-dvh lg:px-12 lg:pb-14">
            <div className="feed-focus" data-active={activeIndex === 1}>
              <div className="max-w-2xl rounded-[30px] bg-[#FFF9F3]/86 p-6 shadow-2xl backdrop-blur-xl sm:p-8">
                <div className="flex items-center justify-between gap-3"><Badge className="border-0 bg-[#EAF1FF] text-[#2563EB]">本周洞察 · AI 建议</Badge><button onClick={() => toast("将展示来源、限制和生成信息")} className="text-xs font-semibold text-[#2563EB]">查看依据</button></div>
                <h2 className="mt-4 font-story text-3xl font-black leading-tight sm:text-4xl">“先听完”正在成为<br />你们的新默契。</h2>
                <p className="mt-4 text-sm leading-7 text-slate-600 sm:text-base">过去 7 天，你记录了 3 次完整倾听。系统只看见行动事实，不评价谁做得更好。</p>
                <div className="mt-6 flex flex-wrap gap-3"><button onClick={() => { setAdopted(true); toast.success("已采纳为下周练习"); }} className={`rounded-full px-5 py-3 text-sm font-bold text-white ${adopted ? "bg-[#16866D]" : "bg-[#2563EB]"}`}>{adopted ? "已采纳" : "采纳这个建议"}</button><button onClick={() => toast("已标记为暂不处理")} className="rounded-full border border-[#BFCDEC] bg-white px-5 py-3 text-sm font-semibold text-[#2563EB]">暂不处理</button></div>
              </div>
              <div className="mt-5 flex justify-end"><ActionRail light /></div>
            </div>
          </div>
        </section>

        <section data-feed-index="2" className="feed-panel relative min-h-full overflow-hidden bg-[#FFF9F3] px-5 py-12 text-[#10213E] sm:px-9 lg:grid lg:min-h-dvh lg:place-items-center lg:px-12">
          <div className="feed-focus mx-auto grid max-w-3xl items-center gap-8 lg:grid-cols-[1fr_1.05fr]" data-active={activeIndex === 2}>
            <div className="relative mx-auto grid h-56 w-56 place-items-center rounded-full bg-[#E6F5F1] shadow-[0_24px_80px_rgba(22,134,109,.18)] sm:h-64 sm:w-64">
              <AchievementBurst active={activeIndex === 2} />
              <div className="absolute inset-3 rounded-full border border-dashed border-[#16866D]/30" />
              <img src="/manus-storage/aifamily-achievement-emblem_3e4238f3.png" alt="共同倾听者成就徽章" className={`relative h-40 w-40 object-contain ${activeIndex === 2 ? "achievement-badge-pop" : ""}`} />
              <span className="absolute -right-2 top-8 rounded-full bg-[#16866D] px-3 py-1.5 text-xs font-bold text-white shadow-lg">新成就</span>
            </div>
            <div className="text-center lg:text-left"><Badge className="border-0 bg-[#E6F5F1] text-[#16866D]">真实行动达成</Badge><h2 className="mt-4 font-story text-4xl font-black leading-tight sm:text-5xl">共同倾听者</h2><p className="mt-4 text-base leading-8 text-slate-600">连续 7 天，在家庭对话里先听完彼此。它不是一个分数，而是一段共同做到的经历。</p><div className="mt-6 flex flex-wrap justify-center gap-3 lg:justify-start"><button onClick={() => toast("成就卡已准备分享", { description: "不会包含孩子姓名或家庭隐私。" })} className="flex items-center gap-2 rounded-full bg-[#F28C45] px-5 py-3 text-sm font-bold text-white"><Share2 className="h-4 w-4" />生成隐私友好分享卡</button><button onClick={() => toast.success("已收藏到家庭时光轴")} className="rounded-full border border-[#B9DDD4] bg-white px-5 py-3 text-sm font-semibold text-[#16866D]">收藏到时光轴</button></div></div>
          </div>
          <div className="absolute bottom-6 left-1/2 flex -translate-x-1/2 items-center gap-2 text-xs font-semibold text-slate-400"><ArrowUp className="h-4 w-4" />上滑回看今天</div>
        </section>
      </div>
    </CustomerShell>
  );
}

function ActionRail({ light = false }: { light?: boolean }) {
  const color = light ? "text-[#10213E]" : "text-white";
  return <div className={`flex items-center gap-4 ${color}`}><button onClick={() => toast("已送出一个鼓励")} aria-label="鼓励" className="grid place-items-center gap-1 text-[10px]"><span className="grid h-10 w-10 place-items-center rounded-full bg-white/18 backdrop-blur"><HeartHandshake className="h-5 w-5" /></span>鼓励</button><button onClick={() => toast("家庭讨论将在接入 API 后开放")} aria-label="讨论" className="grid place-items-center gap-1 text-[10px]"><span className="grid h-10 w-10 place-items-center rounded-full bg-white/18 backdrop-blur"><MessageCircleMore className="h-5 w-5" /></span>讨论</button><button onClick={() => toast.success("已收藏")} aria-label="收藏" className="grid place-items-center gap-1 text-[10px]"><span className="grid h-10 w-10 place-items-center rounded-full bg-white/18 backdrop-blur"><Bookmark className="h-5 w-5" /></span>收藏</button></div>;
}
