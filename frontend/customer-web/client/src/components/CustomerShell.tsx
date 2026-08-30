/* 抖音式单焦点框架：左侧旅程导航、中间沉浸流、右侧行动反馈；移动端改为底部导航。 */
import { MultimodalComposer } from "@/components/MultimodalComposer";
import { GrowthRing } from "@/components/GrowthRing";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { BookOpenText, CalendarCheck2, Compass, Flame, HeartHandshake, Home, Lightbulb, Map, Plus, ShieldCheck, UsersRound } from "lucide-react";
import { type ReactNode, useState } from "react";
import { Link, useLocation } from "wouter";

const nav = [
  { href: "/", label: "成长流", icon: Home },
  { href: "/understand", label: "理解家庭", icon: Lightbulb },
  { href: "/journey", label: "成长计划", icon: Map },
  { href: "/support", label: "专业支持", icon: HeartHandshake },
  { href: "/family", label: "权益与家庭", icon: UsersRound },
];

const secondaryNav = [
  { href: "/moments", label: "家庭时光", icon: BookOpenText },
  { href: "/community", label: "家庭互助", icon: Compass },
];

export function CustomerShell({ children, immersive = false }: { children: ReactNode; immersive?: boolean }) {
  const [location] = useLocation();
  const [composerOpen, setComposerOpen] = useState(false);
  return (
    <div className="min-h-dvh bg-[#FFF9F3] text-[#10213E]">
      <header className="fixed inset-x-0 top-0 z-40 flex h-16 items-center justify-between border-b border-[#EADFD3]/70 bg-[#FFF9F3]/88 px-4 backdrop-blur-xl lg:hidden">
        <Link href="/" className="flex items-center gap-2.5">
          <img src="/manus-storage/aifamily-brand-mark-v2_01372a6a.png" alt="AiFamily" className="h-9 w-9 object-contain" />
          <div><div className="font-score text-[15px] font-extrabold tracking-tight">AiFamily</div><div className="text-[10px] font-semibold text-slate-500">把理解变成行动</div></div>
        </Link>
        <Link href="/profile"><Avatar className="h-9 w-9 border-2 border-white shadow"><AvatarFallback className="bg-[#EAF1FF] font-bold text-[#2563EB]">林</AvatarFallback></Avatar></Link>
      </header>

      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[244px] flex-col border-r border-[#EADFD3]/80 bg-[#FFF9F3]/92 px-5 py-7 backdrop-blur-xl lg:flex">
        <Link href="/" className="flex items-center gap-3 px-2">
          <img src="/manus-storage/aifamily-brand-mark-v2_01372a6a.png" alt="AiFamily" className="h-11 w-11 object-contain" />
          <div><div className="font-score text-lg font-extrabold tracking-tight">AiFamily</div><div className="text-[11px] font-semibold text-slate-500">家庭成长空间</div></div>
        </Link>
        <div className="mt-8 rounded-3xl bg-[#FFF1E6] p-4">
          <div className="flex items-center justify-between"><Badge className="border-0 bg-white text-[#D66A27]">林家 · 第 2 阶段</Badge><Flame className="h-4 w-4 text-[#F28C45]" /></div>
          <p className="mt-3 font-story text-lg font-bold leading-7">今天，只把一件小事做好。</p>
        </div>
        <nav className="mt-6 space-y-1.5" aria-label="主要导航">
          {nav.map((item) => {
            const active = item.href === "/" ? location === "/" : location.startsWith(item.href);
            const Icon = item.icon;
            return <Link key={item.href} href={item.href} className={`group flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-semibold transition-colors ${active ? "bg-[#10213E] text-white shadow-lg shadow-slate-300" : "text-slate-600 hover:bg-white hover:text-[#10213E]"}`}><Icon className={`h-5 w-5 ${active ? "text-[#F28C45]" : "text-slate-400 group-hover:text-[#2563EB]"}`} />{item.label}</Link>;
          })}
        </nav>
        <Link href="/today" className="mt-5 flex items-center justify-center gap-2 rounded-full bg-[#F28C45] px-5 py-3.5 text-sm font-bold text-white shadow-xl shadow-orange-200 hover:bg-[#DE7731]"><CalendarCheck2 className="h-5 w-5" />进入今日行动</Link>
        <div className="mt-6 border-t border-[#EADFD3] pt-5"><p className="px-3 text-[10px] font-bold tracking-[.18em] text-slate-400">记录与连接</p><div className="mt-2 space-y-1">{secondaryNav.map((item) => { const Icon = item.icon; const active = location.startsWith(item.href); return <Link key={item.href} href={item.href} className={`flex items-center gap-3 rounded-2xl px-4 py-2.5 text-sm font-semibold ${active ? "bg-[#EAF1FF] text-[#2563EB]" : "text-slate-500 hover:bg-white hover:text-[#10213E]"}`}><Icon className="h-4.5 w-4.5" />{item.label}</Link>; })}</div></div>
        <button onClick={() => setComposerOpen(true)} className="mt-4 flex items-center justify-center gap-2 rounded-full border border-[#F4C8A9] bg-white px-5 py-3 text-sm font-bold text-[#D66A27] hover:bg-[#FFF1E6]"><Plus className="h-5 w-5" />记录这一刻</button>
        <div className="mt-auto rounded-2xl border border-[#D9E4FF] bg-[#F3F7FF] p-3.5 text-xs leading-5 text-[#1D4EAE]"><div className="flex items-center gap-2 font-bold"><ShieldCheck className="h-4 w-4" />体验数据模式</div><p className="mt-1 text-[#5071AE]">未连接家庭 API，不会上传真实家庭内容。</p></div>
      </aside>

      <main className={`min-h-dvh pt-16 pb-24 lg:pb-0 lg:pt-0 ${immersive ? "lg:ml-[244px] xl:mr-[292px]" : "lg:ml-[244px] xl:mr-[292px]"}`}>{children}</main>

      <aside className="fixed inset-y-0 right-0 z-20 hidden w-[292px] border-l border-[#EADFD3]/80 bg-white/55 px-5 py-7 backdrop-blur-xl xl:block">
        <div className="flex items-center justify-between"><div><p className="text-xs font-semibold text-slate-500">8 月 30 日 · 星期日</p><h2 className="mt-1 font-story text-xl font-bold">林家的今天</h2></div><Avatar className="h-10 w-10 border-2 border-white shadow"><AvatarFallback className="bg-[#EAF1FF] font-bold text-[#2563EB]">林</AvatarFallback></Avatar></div>
        <div className="mt-6 grid place-items-center rounded-[28px] bg-white p-4 shadow-[0_18px_50px_rgba(16,33,62,.08)]"><GrowthRing progress={72} /><div className="mt-1 flex w-full items-center justify-between border-t border-[#F0E7DE] pt-3 text-xs"><span className="text-slate-500">连续行动</span><strong className="font-score text-base text-[#F28C45]">7 天</strong></div></div>
        <div className="mt-5 rounded-[28px] bg-[#10213E] p-5 text-white shadow-xl shadow-slate-300">
          <div className="flex items-center gap-2 text-xs font-bold text-[#8EB2FF]"><Compass className="h-4 w-4" />下一步</div>
          <h3 className="mt-3 font-story text-xl font-bold leading-8">晚饭后，先听完孩子的三句话。</h3>
          <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/15"><div className="h-full w-2/3 rounded-full bg-[#F28C45]" /></div>
          <p className="mt-2 text-xs text-slate-300">预计 3 分钟 · 今晚 19:30</p>
        </div>
        <Link href="/achievements" className="mt-5 flex items-center gap-3 rounded-[24px] border border-[#DCEFEA] bg-[#F3FBF8] p-4 text-sm font-semibold text-[#126C59]"><img src="/manus-storage/aifamily-achievement-emblem_3e4238f3.png" alt="共同倾听成就徽章" className="h-12 w-12 object-contain" /><span>距“共同倾听者”<small className="mt-1 block font-normal text-[#4B8F80]">还差 1 次家庭行动</small></span></Link>
      </aside>

      <nav className="fixed inset-x-0 bottom-0 z-40 grid h-[76px] grid-cols-5 border-t border-[#EADFD3] bg-[#FFFCF8]/94 px-2 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl lg:hidden" aria-label="移动端导航">
        {nav.slice(0, 2).map((item) => <MobileNavItem key={item.href} item={item} active={location === item.href} />)}
        <button onClick={() => setComposerOpen(true)} aria-label="记录这一刻" className="relative grid place-items-center"><span className="soft-pulse absolute -top-4 grid h-14 w-14 place-items-center rounded-2xl bg-[#F28C45] text-white shadow-xl"><Plus className="h-7 w-7" /></span><span className="mt-9 text-[10px] font-bold text-[#D66A27]">记录</span></button>
        {nav.slice(3, 5).map((item) => <MobileNavItem key={item.href} item={item} active={location === item.href} />)}
      </nav>
      <MultimodalComposer open={composerOpen} onOpenChange={setComposerOpen} />
    </div>
  );
}

function MobileNavItem({ item, active }: { item: (typeof nav)[number]; active: boolean }) {
  const Icon = item.icon;
  return <Link href={item.href} className={`grid place-items-center content-center gap-1 text-[10px] font-bold ${active ? "text-[#10213E]" : "text-slate-400"}`}><Icon className={`h-5 w-5 ${active ? "text-[#F28C45]" : ""}`} />{item.label}</Link>;
}
