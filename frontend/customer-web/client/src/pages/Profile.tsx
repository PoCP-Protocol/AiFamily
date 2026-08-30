/* 我的页面强调家庭权限、数据同意和 API 连接状态，而不是消费型等级中心。 */
import { CustomerShell } from "@/components/CustomerShell";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Bell, ChevronRight, Database, KeyRound, ShieldCheck, Sparkles, UsersRound } from "lucide-react";

const settings = [
  { title: "家庭成员与权限", subtitle: "家长、孩子与共同照护人", icon: UsersRound },
  { title: "隐私与同意", subtitle: "管理语音、图片和服务授权", icon: ShieldCheck },
  { title: "登录与设备", subtitle: "会话、设备与安全提醒", icon: KeyRound },
  { title: "通知偏好", subtitle: "只接收对家庭真正有用的提醒", icon: Bell },
];

export default function Profile() { return <CustomerShell><div className="mx-auto max-w-4xl px-5 py-8 sm:px-8 lg:py-12"><section className="enter-rise relative overflow-hidden rounded-[36px] bg-[#10213E] p-6 text-white sm:p-9"><div className="absolute -right-12 -top-12 h-56 w-56 rounded-full bg-[#2563EB]/40 blur-2xl" /><div className="relative flex flex-col justify-between gap-7 sm:flex-row sm:items-center"><div className="flex items-center gap-4"><Avatar className="h-20 w-20 border-4 border-white/15"><AvatarFallback className="bg-[#FFF1E6] text-2xl font-black text-[#F28C45]">林</AvatarFallback></Avatar><div><Badge className="border-white/15 bg-white/10 text-white">家庭管理员</Badge><h1 className="mt-2 font-story text-3xl font-black">林家的成长空间</h1><p className="mt-1 text-sm text-slate-300">2 位家长 · 1 位孩子 · 共同照护</p></div></div><img src="/manus-storage/aifamily-brand-mark-v2_01372a6a.png" alt="AiFamily 品牌标志" className="hidden h-24 w-24 object-contain sm:block" /></div></section>
    <div className="mt-6 grid gap-5 md:grid-cols-[1fr_.72fr]"><section className="space-y-3">{settings.map((item) => { const Icon = item.icon; return <button key={item.title} className="flex w-full items-center gap-4 rounded-[24px] bg-white p-4 text-left shadow-[0_10px_30px_rgba(16,33,62,.05)] hover:-translate-y-0.5"><span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-[#FFF1E6] text-[#F28C45]"><Icon className="h-5 w-5" /></span><span className="min-w-0 flex-1"><strong className="block text-sm">{item.title}</strong><small className="mt-1 block text-slate-500">{item.subtitle}</small></span><ChevronRight className="h-5 w-5 text-slate-300" /></button>; })}</section>
    <aside className="space-y-5"><div className="rounded-[28px] border border-[#D8E4FF] bg-[#F3F7FF] p-5"><div className="flex items-center gap-2 text-xs font-bold text-[#2563EB]"><Database className="h-4 w-4" />家庭 API</div><div className="mt-4 flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-full bg-[#F28C45]" /><strong className="text-sm">体验数据模式</strong></div><p className="mt-2 text-xs leading-5 text-[#5071AE]">未配置 `VITE_FAMILY_API_BASE_URL`，所有记录仅保留在当前浏览器体验中。</p></div><div className="rounded-[28px] bg-[#FFF1E6] p-5"><div className="flex items-center gap-2 text-xs font-bold text-[#D66A27]"><Sparkles className="h-4 w-4" />AI 边界</div><p className="mt-3 text-sm leading-7 text-slate-600">AI 只协助形成视角、建议与草案。家庭事实、计划确认和高影响决定必须由人完成。</p></div></aside></div></div></CustomerShell>; }
