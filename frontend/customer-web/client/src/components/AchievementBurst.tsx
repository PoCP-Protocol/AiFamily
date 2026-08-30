/* 成就反馈只庆祝共同完成，不包含排名、分数或消费等级。 */
import type { CSSProperties } from "react";

const particles = [
  [-74, -52, "#F28C45"], [4, -82, "#2563EB"], [72, -48, "#16866D"],
  [86, 12, "#F28C45"], [55, 68, "#2563EB"], [-8, 84, "#16866D"],
  [-67, 61, "#F28C45"], [-88, 4, "#2563EB"],
] as const;

export function AchievementBurst({ active, className = "" }: { active: boolean; className?: string }) {
  if (!active) return null;
  return (
    <div aria-hidden="true" className={`pointer-events-none absolute inset-0 grid place-items-center ${className}`}>
      <span className="achievement-halo absolute h-32 w-32 rounded-full border-2 border-[#F28C45]/60" />
      <span className="achievement-halo achievement-halo-delay absolute h-32 w-32 rounded-full border border-[#2563EB]/45" />
      {particles.map(([x, y, color], index) => (
        <span key={`${x}-${y}`} className="achievement-particle absolute h-2.5 w-2.5 rounded-full" style={{ "--particle-x": `${x}px`, "--particle-y": `${y}px`, "--particle-delay": `${index * 45}ms`, backgroundColor: color } as CSSProperties} />
      ))}
    </div>
  );
}
