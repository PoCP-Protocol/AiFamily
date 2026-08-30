/* 成就中心以家庭轨迹带呈现共同走过的路径；“预览解锁”只用于可用性测试。 */
import { AchievementBurst } from "@/components/AchievementBurst";
import { CustomerShell } from "@/components/CustomerShell";
import { Badge } from "@/components/ui/badge";
import { Check, Clock3, Flag, LockKeyhole, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";

const milestones = [
  { name: "看见彼此", detail: "完成第一次家庭理解与确认", state: "earned", caption: "8 月 12 日" },
  { name: "共同倾听者", detail: "连续 7 天先听完彼此", state: "earned", caption: "今天解锁" },
  { name: "温柔复盘者", detail: "一起完成 3 次家庭复盘", state: "progress", caption: "已完成 2/3" },
  { name: "共同选择者", detail: "共同确认第一个家庭计划", state: "locked", caption: "下一阶段" },
] as const;

export default function Achievements() {
  const [previewIndex, setPreviewIndex] = useState<number | null>(null);
  useEffect(() => {
    if (previewIndex === null) return;
    const timer = window.setTimeout(() => setPreviewIndex(null), 1500);
    return () => window.clearTimeout(timer);
  }, [previewIndex]);

  return (
    <CustomerShell>
      <div className="mx-auto max-w-5xl px-5 py-8 sm:px-8 lg:py-12">
        <div className="enter-rise flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
          <div><Badge className="border-0 bg-[#E6F5F1] text-[#16866D]"><Sparkles className="mr-1.5 h-3.5 w-3.5" />家庭共同成就</Badge><h1 className="mt-4 font-story text-4xl font-black sm:text-5xl">不是收集奖牌，<br />是记住一起走过。</h1><p className="mt-3 max-w-xl leading-7 text-slate-600">没有家庭等级，也不与别人比较。轨迹上的每个点，只记录你们共同完成的真实行动。</p></div>
          <div className="rounded-[30px] bg-[#FFF1E6] px-6 py-4"><span className="text-xs font-bold text-[#D66A27]">当前家庭轨迹</span><strong className="font-score mt-1 block text-3xl text-[#10213E]">第 7 天</strong></div>
        </div>

        <section className="relative mt-10 overflow-hidden rounded-[38px] bg-white px-5 py-9 shadow-[0_24px_70px_rgba(16,33,62,.07)] sm:px-10 sm:py-12">
          <div className="absolute left-[47px] top-14 h-[calc(100%-112px)] w-1 rounded-full bg-gradient-to-b from-[#16866D] from-0% via-[#F28C45] via-58% to-[#DDE5F1] to-58% sm:left-1/2 sm:-translate-x-1/2" />
          <div className="space-y-8 sm:space-y-10">
            {milestones.map((milestone, index) => {
              const earned = milestone.state === "earned";
              const active = milestone.state === "progress";
              return (
                <article key={milestone.name} className={`relative grid grid-cols-[64px_1fr] items-center gap-4 sm:grid-cols-[1fr_86px_1fr] ${index % 2 ? "" : "sm:text-right"}`}>
                  <div className={`hidden sm:block ${index % 2 ? "sm:order-3" : "sm:order-1"}`}>{index % 2 === 0 && <MilestoneCopy milestone={milestone} active={active} onPreview={() => setPreviewIndex(index)} />}</div>
                  <div className="relative z-10 grid h-14 w-14 place-items-center rounded-full border-4 border-white shadow-lg sm:order-2 sm:h-17 sm:w-17 sm:justify-self-center" style={{ background: earned ? "#16866D" : active ? "#F28C45" : "#E9EDF3", color: earned || active ? "white" : "#8A96A8" }}>
                    <AchievementBurst active={previewIndex === index} />
                    <span className={previewIndex === index ? "achievement-badge-pop" : ""}>{earned ? <Check className="h-6 w-6" /> : active ? <Clock3 className="h-6 w-6" /> : <LockKeyhole className="h-5 w-5" />}</span>
                  </div>
                  <div className="sm:hidden"><MilestoneCopy milestone={milestone} active={active} onPreview={() => setPreviewIndex(index)} /></div>
                  <div className={`hidden sm:block ${index % 2 ? "sm:order-1" : "sm:order-3"}`}>{index % 2 === 1 && <MilestoneCopy milestone={milestone} active={active} onPreview={() => setPreviewIndex(index)} />}</div>
                </article>
              );
            })}
          </div>
          <div className="mt-10 flex items-center gap-3 rounded-[26px] bg-[#10213E] p-5 text-white"><span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-[#F28C45]"><Flag className="h-5 w-5" /></span><div><strong className="font-story text-lg">下一个可共同做到的小点</strong><p className="mt-1 text-xs leading-5 text-slate-300">完成一次家庭复盘。由家长发起，不会根据孩子表现自动解锁。</p></div></div>
        </section>

        <div className="mt-8 rounded-[30px] bg-[#FFF1E6] p-6 sm:flex sm:items-center sm:justify-between"><div><strong className="font-story text-xl">成就可以分享，但隐私不必分享。</strong><p className="mt-2 text-sm text-slate-600">分享卡默认隐藏姓名、头像、孩子信息和具体家庭记录。</p></div><button className="mt-4 rounded-full bg-[#F28C45] px-5 py-3 text-sm font-bold text-white sm:mt-0">管理分享隐私</button></div>
      </div>
    </CustomerShell>
  );
}

function MilestoneCopy({ milestone, active, onPreview }: { milestone: (typeof milestones)[number]; active: boolean; onPreview: () => void }) {
  return <div className={`rounded-[24px] p-4 ${active ? "bg-[#FFF1E6]" : "bg-[#FFF9F3]"}`}><p className={`text-xs font-bold ${milestone.state === "earned" ? "text-[#16866D]" : active ? "text-[#D66A27]" : "text-slate-400"}`}>{milestone.caption}</p><h2 className="mt-1 font-story text-xl font-bold">{milestone.name}</h2><p className="mt-1 text-sm leading-6 text-slate-500">{milestone.detail}</p>{milestone.state !== "locked" && <button onClick={onPreview} className="mt-2 text-xs font-bold text-[#D66A27]">预览解锁反馈</button>}</div>;
}
