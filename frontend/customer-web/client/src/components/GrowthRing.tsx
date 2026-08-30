/* 成长光环只表达已完成行动，不表达家庭评分、排名或诊断。 */
export function GrowthRing({ progress = 72, size = 116 }: { progress?: number; size?: number }) {
  const radius = 45;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - progress / 100);
  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }} aria-label={`本周行动完成 ${progress}%`}>
      <svg viewBox="0 0 112 112" className="absolute inset-0 -rotate-90" aria-hidden="true">
        <circle cx="56" cy="56" r={radius} fill="none" stroke="#F5E8DC" strokeWidth="8" />
        <circle cx="56" cy="56" r={radius} fill="none" stroke="#F28C45" strokeWidth="8" strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={offset} />
        <circle cx="56" cy="56" r="35" fill="none" stroke="#2563EB" strokeWidth="2" strokeDasharray="3 8" opacity=".55" />
      </svg>
      <div className="relative text-center">
        <div className="font-score text-2xl font-extrabold text-[var(--brand-navy)]">{progress}%</div>
        <div className="text-[11px] font-semibold text-slate-500">本周行动</div>
      </div>
      <span className="absolute right-[12%] top-[19%] h-3 w-3 rounded-full border-2 border-white bg-[var(--brand-green)] shadow-sm" aria-hidden="true" />
    </div>
  );
}
