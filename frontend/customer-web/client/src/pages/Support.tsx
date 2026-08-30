/* 专业支持工作台：以浏览器模拟数据完成服务选择、知情同意、预约意向、改期、撤回和取消测试。 */
import { CustomerShell } from "@/components/CustomerShell";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { createMockBooking, createMockConsent, loadMockBooking, mockOfferings, mockSubjects, saveMockBooking, type MockBookingRequest, type MockConsentGrant, type MockServiceOffering } from "@/lib/mock-service";
import { CalendarDays, Check, CheckCircle2, ChevronLeft, ChevronRight, Clock3, FileCheck2, HeartHandshake, MessageCircleMore, RefreshCcw, ShieldCheck, UserRound, UsersRound, Video, XCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

type View = "discover" | "mine" | "events";

export default function Support() {
  const [view, setView] = useState<View>("discover");
  const [selected, setSelected] = useState<MockServiceOffering | null>(null);
  const [step, setStep] = useState(1);
  const [slotId, setSlotId] = useState("");
  const [subjectId, setSubjectId] = useState(mockSubjects[0].id);
  const [needSummary, setNeedSummary] = useState("");
  const [consentChecks, setConsentChecks] = useState({ scope: false, boundary: false, withdrawal: false });
  const [draftConsent, setDraftConsent] = useState<MockConsentGrant | null>(null);
  const [booking, setBooking] = useState<MockBookingRequest | null>(() => loadMockBooking());
  const [successOpen, setSuccessOpen] = useState(false);
  const [rescheduleOpen, setRescheduleOpen] = useState(false);
  const [nextSlotId, setNextSlotId] = useState("");

  const offeringForBooking = useMemo(() => mockOfferings.find((item) => item.id === booking?.serviceOfferingId) ?? null, [booking]);
  const slotForBooking = offeringForBooking?.slots.find((item) => item.id === booking?.availabilitySlotId) ?? null;
  const subjectForBooking = mockSubjects.find((item) => item.id === booking?.subjectPersonId) ?? null;
  const selectedSlot = selected?.slots.find((item) => item.id === slotId) ?? null;
  const selectedSubject = mockSubjects.find((item) => item.id === subjectId) ?? null;

  const beginBooking = (offering: MockServiceOffering) => {
    setSelected(offering);
    setStep(1);
    setSlotId("");
    setSubjectId(mockSubjects[0].id);
    setNeedSummary("");
    setConsentChecks({ scope: false, boundary: false, withdrawal: false });
    setDraftConsent(null);
  };

  const next = () => {
    if (step === 2 && !slotId) return toast.error("请选择一个时间偏好");
    if (step === 3 && !subjectId) return toast.error("请选择本次服务对象");
    setStep((value) => Math.min(5, value + 1));
  };

  const grantConsent = () => {
    if (!consentChecks.scope || !consentChecks.boundary || !consentChecks.withdrawal) return toast.error("请确认三项知情同意内容");
    const consent = createMockConsent(subjectId);
    setDraftConsent(consent);
    setStep(5);
    toast.success("模拟 Consent 已生成", { description: "仅用于本次浏览器可用性测试。" });
  };

  const submitBooking = () => {
    if (!selected || !slotId || !draftConsent) return toast.error("预约信息不完整");
    const nextBooking = createMockBooking({ offeringId: selected.id, slotId, subjectPersonId: subjectId, needSummary: needSummary.trim(), consent: draftConsent });
    setBooking(nextBooking);
    saveMockBooking(nextBooking);
    setSelected(null);
    setSuccessOpen(true);
    navigator.vibrate?.([25, 35, 25]);
  };

  const updateBooking = (updater: (current: MockBookingRequest) => MockBookingRequest) => {
    if (!booking) return;
    const nextBooking = updater(booking);
    setBooking(nextBooking);
    saveMockBooking(nextBooking);
  };

  const withdrawConsent = () => {
    updateBooking((current) => ({ ...current, consent: { ...current.consent, status: "WITHDRAWN", withdrawnAt: new Date().toISOString() }, updatedAt: new Date().toISOString() }));
    toast.success("模拟 Consent 已撤回", { description: "预约历史保留；新的服务处理应立即停止。" });
  };

  const cancelBooking = () => {
    updateBooking((current) => ({ ...current, status: "CANCELLED", updatedAt: new Date().toISOString() }));
    toast.success("模拟预约意向已取消", { description: "不会触发退款或任何外部操作。" });
  };

  const reschedule = () => {
    if (!nextSlotId) return toast.error("请选择新时段");
    updateBooking((current) => ({ ...current, availabilitySlotId: nextSlotId, updatedAt: new Date().toISOString() }));
    setRescheduleOpen(false);
    toast.success("模拟时间偏好已更新");
  };

  return (
    <CustomerShell>
      <div className="mx-auto max-w-6xl px-5 py-8 sm:px-8 lg:py-10">
        <div className="flex flex-col justify-between gap-5 md:flex-row md:items-end">
          <div><Badge className="border-0 bg-[#EAF1FF] text-[#2563EB]"><HeartHandshake className="mr-1.5 h-3.5 w-3.5" />专业支持</Badge><h1 className="mt-3 font-story text-4xl font-black sm:text-5xl">需要帮助时，找到适合此刻的支持。</h1><p className="mt-3 max-w-2xl leading-7 text-slate-600">以模拟数据测试服务选择、Consent、预约、改期与取消。不会扣款，也不会联系真实顾问。</p></div>
          <Badge variant="outline" className="w-fit border-[#F4C8A9] bg-[#FFF1E6] px-3 py-2 text-[#D66A27]">可用性测试 · 模拟服务数据</Badge>
        </div>

        <div className="mt-8 inline-flex rounded-full bg-white p-1.5 shadow-sm">{[["discover","发现支持"],["events","主题活动"],["mine","我的安排"]].map(([id,label]) => <button key={id} onClick={() => setView(id as View)} className={`rounded-full px-5 py-2.5 text-sm font-bold ${view === id ? "bg-[#10213E] text-white" : "text-slate-500"}`}>{label}{id === "mine" && booking && <span className="ml-2 inline-grid h-5 min-w-5 place-items-center rounded-full bg-[#F28C45] px-1 text-[10px] text-white">1</span>}</button>)}</div>

        {view === "discover" && <div className="mt-7 grid gap-5 lg:grid-cols-2">{mockOfferings.map((offering) => <article key={offering.id} className="group overflow-hidden rounded-[32px] bg-white shadow-[0_20px_60px_rgba(16,33,62,.07)]"><div className="relative h-52 overflow-hidden bg-[#DCE7FF]"><img src={offering.image} alt={offering.title} className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-[1.03]" /><div className="absolute inset-0 bg-gradient-to-t from-[#10213E]/75 to-transparent" /><div className="absolute bottom-5 left-5 right-5 text-white"><Badge className="border-white/20 bg-white/15 text-white backdrop-blur">模拟服务资料</Badge><h2 className="mt-3 font-story text-2xl font-bold">{offering.title}</h2></div></div><div className="p-5 sm:p-6"><div className="flex flex-wrap gap-2 text-xs text-slate-500"><span className="rounded-full bg-[#F3F7FF] px-3 py-1.5">{offering.expert}</span><span className="rounded-full bg-[#FFF1E6] px-3 py-1.5">{offering.channel}</span><span className="rounded-full bg-slate-50 px-3 py-1.5">{offering.duration}</span></div><p className="mt-4 text-sm leading-7 text-slate-600">{offering.fit}</p><div className="mt-4 flex items-start gap-2 rounded-2xl bg-[#FFF9F3] p-3 text-xs leading-5 text-slate-500"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-[#2563EB]" />{offering.boundary}</div><button onClick={() => beginBooking(offering)} className="mt-5 flex w-full items-center justify-between rounded-full bg-[#10213E] px-5 py-3.5 text-sm font-bold text-white">开始模拟预约<ChevronRight className="h-4 w-4" /></button></div></article>)}</div>}

        {view === "events" && <div className="mt-7 grid gap-5 lg:grid-cols-[1.2fr_.8fr]"><article className="rounded-[34px] bg-[#F28C45] p-7 text-white shadow-xl shadow-orange-200 sm:p-9"><Badge className="border-white/20 bg-white/15 text-white">线上主题小组 · 模拟数据</Badge><h2 className="mt-5 font-story text-4xl font-black">冲突之后，怎样重新开口</h2><p className="mt-4 max-w-xl leading-8 text-white/82">围绕暂停、复述和共同约定三个练习展开。活动介绍不承诺家庭变化，保存意向不等于名额确认。</p><div className="mt-8 flex flex-wrap gap-5 text-sm"><span className="flex items-center gap-2"><CalendarDays className="h-4 w-4" />9 月 6 日</span><span className="flex items-center gap-2"><Clock3 className="h-4 w-4" />19:30–20:30</span><span className="flex items-center gap-2"><Video className="h-4 w-4" />线上</span></div><button onClick={() => toast.success("模拟活动意向已保存")} className="mt-8 rounded-full bg-white px-6 py-3.5 text-sm font-bold text-[#D66A27]">保存模拟活动意向</button></article><aside className="rounded-[34px] bg-white p-7 shadow-[0_20px_60px_rgba(16,33,62,.07)]"><UsersRound className="h-8 w-8 text-[#2563EB]" /><h3 className="mt-4 font-story text-2xl font-bold">适合谁</h3><div className="mt-5 space-y-3 text-sm text-slate-600"><p className="flex gap-2"><Check className="h-4 w-4 shrink-0 text-[#16866D]" />冲突后常常不知道怎样重新开始</p><p className="flex gap-2"><Check className="h-4 w-4 shrink-0 text-[#16866D]" />愿意先从家长的一次小行动开始</p><p className="flex gap-2"><Check className="h-4 w-4 shrink-0 text-[#16866D]" />同意在活动边界内讨论家庭场景</p></div></aside></div>}

        {view === "mine" && <MyBooking booking={booking} offering={offeringForBooking} slot={slotForBooking} subjectName={subjectForBooking?.name ?? "家庭成员"} onDiscover={() => setView("discover")} onReschedule={() => { setNextSlotId(booking?.availabilitySlotId ?? ""); setRescheduleOpen(true); }} onWithdraw={withdrawConsent} onCancel={cancelBooking} />}

        <Sheet open={Boolean(selected)} onOpenChange={(open) => !open && setSelected(null)}>
          <SheetContent side="right" className="w-full overflow-y-auto border-l-[#EADFD3] bg-[#FFF9F3] p-5 sm:max-w-xl sm:p-8">
            <SheetHeader className="text-left"><div className="mb-2 flex items-center justify-between gap-3"><Badge className="border-0 bg-[#FFF1E6] text-[#D66A27]">模拟预约 · 第 {step}/5 步</Badge><span className="text-xs text-slate-400">不会扣款</span></div><SheetTitle className="font-story text-3xl font-black text-[#10213E]">{["了解服务","选择时间","确认服务对象","知情同意","核对并提交"][step - 1]}</SheetTitle><SheetDescription>所有数据只保存在当前浏览器，用于流程可用性测试。</SheetDescription></SheetHeader>
            <div className="mt-6 flex gap-1.5">{[1,2,3,4,5].map((index) => <span key={index} className={`h-1.5 flex-1 rounded-full ${index <= step ? "bg-[#F28C45]" : "bg-[#EADFD3]"}`} />)}</div>
            {selected && <div className="mt-7">
              {step === 1 && <ServiceIntro offering={selected} />}
              {step === 2 && <SlotStep offering={selected} slotId={slotId} setSlotId={setSlotId} />}
              {step === 3 && <SubjectStep subjectId={subjectId} setSubjectId={setSubjectId} needSummary={needSummary} setNeedSummary={setNeedSummary} />}
              {step === 4 && <ConsentStep checks={consentChecks} setChecks={setConsentChecks} onGrant={grantConsent} />}
              {step === 5 && <ReviewStep offering={selected} slot={selectedSlot} subjectName={selectedSubject?.name ?? "家庭成员"} needSummary={needSummary} consent={draftConsent} />}
              {step !== 4 && <div className="mt-7 flex items-center justify-between gap-3"><button onClick={() => step > 1 ? setStep((value) => value - 1) : setSelected(null)} className="flex items-center gap-2 px-3 text-sm font-bold text-slate-500"><ChevronLeft className="h-4 w-4" />{step > 1 ? "上一步" : "退出"}</button>{step < 5 ? <Button onClick={next} className="h-12 rounded-full bg-[#F28C45] px-6 font-bold text-white hover:bg-[#DE7731]">继续<ChevronRight className="ml-1 h-4 w-4" /></Button> : <Button onClick={submitBooking} className="h-12 rounded-full bg-[#F28C45] px-6 font-bold text-white hover:bg-[#DE7731]">提交模拟预约</Button>}</div>}
            </div>}
          </SheetContent>
        </Sheet>

        <Dialog open={successOpen} onOpenChange={setSuccessOpen}><DialogContent className="rounded-[30px] border-0 bg-[#FFF9F3] sm:max-w-md"><DialogHeader className="text-center"><span className="mx-auto grid h-18 w-18 place-items-center rounded-full bg-[#E6F5F1] text-[#16866D]"><CheckCircle2 className="h-9 w-9" /></span><DialogTitle className="mt-4 font-story text-3xl font-black">模拟预约意向已保存</DialogTitle><DialogDescription className="mt-2 leading-7">这不是正式预约：不会扣款、不会锁定顾问时间，也不会联系任何外部人员。</DialogDescription></DialogHeader><div className="mt-3 rounded-2xl bg-white p-4 text-sm"><div className="flex justify-between gap-3"><span className="text-slate-500">体验回执</span><strong>{booking?.bookingRef}</strong></div><div className="mt-2 flex justify-between gap-3"><span className="text-slate-500">状态</span><strong className="text-[#D66A27]">REQUESTED · 待确认</strong></div></div><Button onClick={() => { setSuccessOpen(false); setView("mine"); }} className="mt-2 h-12 rounded-full bg-[#F28C45] font-bold text-white hover:bg-[#DE7731]">查看我的安排</Button></DialogContent></Dialog>

        <Dialog open={rescheduleOpen} onOpenChange={setRescheduleOpen}><DialogContent className="rounded-[30px] bg-[#FFF9F3] sm:max-w-md"><DialogHeader><DialogTitle className="font-story text-2xl font-black">重新选择时间偏好</DialogTitle><DialogDescription>模拟更新不会占用真实时段。</DialogDescription></DialogHeader><div className="mt-3 grid gap-2">{offeringForBooking?.slots.map((slot) => <button key={slot.id} onClick={() => setNextSlotId(slot.id)} className={`flex items-center justify-between rounded-2xl border p-4 text-left ${nextSlotId === slot.id ? "border-[#2563EB] bg-[#EAF1FF]" : "border-[#EADFD3] bg-white"}`}><span><strong className="block text-sm">{slot.date}</strong><small className="mt-1 block text-slate-500">{slot.period}</small></span>{nextSlotId === slot.id && <Check className="h-5 w-5 text-[#2563EB]" />}</button>)}</div><Button onClick={reschedule} className="mt-4 h-12 rounded-full bg-[#F28C45] font-bold text-white">保存模拟时间偏好</Button></DialogContent></Dialog>
      </div>
    </CustomerShell>
  );
}

function ServiceIntro({ offering }: { offering: MockServiceOffering }) { return <div><div className="overflow-hidden rounded-[26px] bg-white shadow-sm"><img src={offering.image} alt={offering.title} className="h-48 w-full object-cover" /><div className="p-5"><Badge className="border-0 bg-[#EAF1FF] text-[#2563EB]">{offering.expert}</Badge><h3 className="mt-3 font-story text-2xl font-bold">{offering.title}</h3><p className="mt-3 text-sm leading-7 text-slate-600">{offering.fit}</p></div></div><div className="mt-4 flex items-start gap-3 rounded-[24px] border border-[#D9E4FF] bg-[#F3F7FF] p-4"><ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-[#2563EB]" /><div><strong className="text-sm text-[#1D4EAE]">服务边界</strong><p className="mt-1 text-xs leading-6 text-[#5071AE]">{offering.boundary}。最终时段需人工确认。</p></div></div></div>; }
function SlotStep({ offering, slotId, setSlotId }: { offering: MockServiceOffering; slotId: string; setSlotId: (value: string) => void }) { return <div className="grid gap-3">{offering.slots.map((slot) => <button key={slot.id} onClick={() => setSlotId(slot.id)} className={`flex items-center justify-between rounded-[22px] border p-4 text-left ${slotId === slot.id ? "border-[#2563EB] bg-[#EAF1FF] text-[#184FBF]" : "border-[#EADFD3] bg-white text-[#10213E]"}`}><span><strong className="block">{slot.date}</strong><small className="mt-1 block text-slate-500">{slot.period} · {offering.channel}</small></span><span className={`grid h-6 w-6 place-items-center rounded-full border ${slotId === slot.id ? "border-[#2563EB] bg-[#2563EB] text-white" : "border-slate-300"}`}>{slotId === slot.id && <Check className="h-3.5 w-3.5" />}</span></button>)}<p className="mt-2 text-xs leading-5 text-slate-500">这是偏好选择，不会立即确认或占用真实时段。</p></div>; }
function SubjectStep({ subjectId, setSubjectId, needSummary, setNeedSummary }: { subjectId: string; setSubjectId: (value: string) => void; needSummary: string; setNeedSummary: (value: string) => void }) { return <div><div className="grid gap-3">{mockSubjects.map((subject) => <button key={subject.id} onClick={() => setSubjectId(subject.id)} className={`flex items-center gap-4 rounded-[22px] border p-4 text-left ${subjectId === subject.id ? "border-[#2563EB] bg-[#EAF1FF]" : "border-[#EADFD3] bg-white"}`}><span className="grid h-11 w-11 place-items-center rounded-2xl bg-white text-[#2563EB]"><UserRound className="h-5 w-5" /></span><span className="flex-1"><strong className="block">{subject.name}</strong><small className="mt-1 block text-slate-500">{subject.role}</small></span>{subjectId === subject.id && <Check className="h-5 w-5 text-[#2563EB]" />}</button>)}</div><label className="mt-6 block text-sm font-bold">这次最希望获得什么帮助？</label><textarea value={needSummary} onChange={(event) => setNeedSummary(event.target.value)} className="mt-3 min-h-28 w-full rounded-[22px] border border-[#EADFD3] bg-white p-4 text-sm outline-none focus:border-[#2563EB]" placeholder="只写本次服务需要知道的内容，不必填写学校、住址等无关信息。" /><div className="mt-3 text-right text-xs text-slate-400">{needSummary.length}/200 · 可留空</div></div>; }
function ConsentStep({ checks, setChecks, onGrant }: { checks: { scope: boolean; boundary: boolean; withdrawal: boolean }; setChecks: (value: { scope: boolean; boundary: boolean; withdrawal: boolean }) => void; onGrant: () => void }) { const rows = [{ key: "scope" as const, title: "我理解本次使用范围", desc: "仅使用服务对象、时间偏好和本次需求摘要进行服务匹配。" },{ key: "boundary" as const, title: "我理解服务与 AI 边界", desc: "服务不做临床诊断或效果承诺，AI 不会替我确认预约。" },{ key: "withdrawal" as const, title: "我知道可以撤回", desc: "撤回后停止新的处理；已形成的审计历史不会被伪造删除。" }]; return <div><div className="rounded-[26px] bg-[#10213E] p-5 text-white"><div className="flex items-center gap-2 text-xs font-bold text-[#8EB2FF]"><FileCheck2 className="h-4 w-4" />Consent · SERVICE_MATCHING</div><h3 className="mt-3 font-story text-2xl font-bold">请在提交前确认用途、范围和撤回方式。</h3><p className="mt-3 text-sm leading-7 text-slate-300">有效范围只限本次服务匹配。模拟授权保存在当前浏览器，不发送到真实后端。</p></div><div className="mt-4 space-y-3">{rows.map((row) => <label key={row.key} className="flex cursor-pointer items-start gap-3 rounded-[22px] bg-white p-4 shadow-sm"><Checkbox checked={checks[row.key]} onCheckedChange={(checked) => setChecks({ ...checks, [row.key]: checked === true })} className="mt-0.5" /><span><strong className="block text-sm">{row.title}</strong><small className="mt-1 block leading-5 text-slate-500">{row.desc}</small></span></label>)}</div><Button onClick={onGrant} disabled={!checks.scope || !checks.boundary || !checks.withdrawal} className="mt-6 h-12 w-full rounded-full bg-[#F28C45] font-bold text-white hover:bg-[#DE7731] disabled:bg-slate-300">确认并生成模拟 Consent</Button><button className="mt-3 w-full text-center text-xs font-semibold text-slate-500">不同意并退出预约</button></div>; }
function ReviewStep({ offering, slot, subjectName, needSummary, consent }: { offering: MockServiceOffering; slot: MockServiceOffering["slots"][number] | null; subjectName: string; needSummary: string; consent: MockConsentGrant | null }) { return <div><div className="rounded-[26px] bg-white p-5 shadow-sm"><ReviewRow label="模拟服务" value={offering.title} /><ReviewRow label="时间偏好" value={slot ? `${slot.date} ${slot.period}` : "未选择"} /><ReviewRow label="服务对象" value={subjectName} /><ReviewRow label="需求摘要" value={needSummary || "未填写"} /><ReviewRow label="Consent" value={consent ? "ACTIVE · 本次服务匹配" : "未生成"} last /></div><div className="mt-4 rounded-[24px] bg-[#FFF1E6] p-4 text-xs leading-6 text-[#8D451D]"><strong>提交后的状态是 REQUESTED。</strong><br />不会自动成为已确认预约，不会扣款，也不会产生服务记录。</div></div>; }
function ReviewRow({ label, value, last = false }: { label: string; value: string; last?: boolean }) { return <div className={`flex items-start justify-between gap-4 py-3 ${last ? "" : "border-b border-[#F0E7DE]"}`}><span className="shrink-0 text-xs text-slate-500">{label}</span><strong className="text-right text-sm">{value}</strong></div>; }
function MyBooking({ booking, offering, slot, subjectName, onDiscover, onReschedule, onWithdraw, onCancel }: { booking: MockBookingRequest | null; offering: MockServiceOffering | null; slot: MockServiceOffering["slots"][number] | null; subjectName: string; onDiscover: () => void; onReschedule: () => void; onWithdraw: () => void; onCancel: () => void }) {
  if (!booking || !offering) return <div className="mt-7 rounded-[34px] border border-dashed border-[#C7D6F5] bg-[#F7FAFF] p-10 text-center"><span className="mx-auto grid h-16 w-16 place-items-center rounded-3xl bg-white text-[#2563EB] shadow-sm"><MessageCircleMore className="h-7 w-7" /></span><h2 className="mt-5 font-story text-2xl font-bold">还没有模拟服务安排</h2><p className="mx-auto mt-3 max-w-lg text-sm leading-7 text-slate-500">完成一次服务选择、Consent 和预约提交后，这里会显示可改期、可撤回和可取消的测试回执。</p><button onClick={onDiscover} className="mt-6 rounded-full bg-[#2563EB] px-6 py-3 text-sm font-bold text-white">开始模拟预约</button></div>;
  const active = booking.status === "REQUESTED";
  const consentActive = booking.consent.status === "ACTIVE";
  return (
    <div className="mt-7 grid gap-5 lg:grid-cols-[1fr_.72fr]">
      <article className="overflow-hidden rounded-[34px] bg-white shadow-[0_20px_60px_rgba(16,33,62,.07)]">
        <div className="flex flex-wrap items-center justify-between gap-3 bg-[#10213E] p-5 text-white">
          <div><p className="text-xs text-slate-300">体验回执 · {booking.bookingRef}</p><h2 className="mt-1 font-story text-2xl font-bold">{offering.title}</h2></div>
          <Badge className={`border-0 ${active ? consentActive ? "bg-[#FFF1E6] text-[#D66A27]" : "bg-[#FCE8E8] text-[#B73B3B]" : "bg-slate-600 text-white"}`}>{!active ? "已取消" : consentActive ? "REQUESTED · 待确认" : "Consent 已撤回"}</Badge>
        </div>
        <div className="p-6">
          <div className="grid gap-4 sm:grid-cols-3"><Summary icon={CalendarDays} label="时间偏好" value={slot ? `${slot.date} ${slot.period}` : "待确认"} /><Summary icon={UserRound} label="服务对象" value={subjectName} /><Summary icon={Video} label="方式" value={offering.channel} /></div>
          {booking.needSummary && <div className="mt-5 rounded-2xl bg-[#FFF9F3] p-4"><p className="text-xs text-slate-400">本次需求摘要</p><p className="mt-2 text-sm leading-6 text-slate-600">{booking.needSummary}</p></div>}
          <div className="mt-6 flex flex-wrap gap-3">
            <button disabled={!active || !consentActive} onClick={onReschedule} className="flex items-center gap-2 rounded-full bg-[#F28C45] px-5 py-3 text-sm font-bold text-white hover:bg-[#DE7731] disabled:bg-slate-300"><RefreshCcw className="h-4 w-4" />重新选择时段</button>
            {active && <AlertDialog><AlertDialogTrigger asChild><button className="rounded-full border border-[#E8B8B8] bg-white px-5 py-3 text-sm font-bold text-[#B73B3B]">取消模拟预约</button></AlertDialogTrigger><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>取消这份模拟预约意向？</AlertDialogTitle><AlertDialogDescription>状态将变为 CANCELLED；不会触发退款或外部通知。</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>返回</AlertDialogCancel><AlertDialogAction onClick={onCancel} className="bg-[#B73B3B] text-white">确认取消</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog>}
          </div>
        </div>
      </article>
      <aside className="h-fit rounded-[30px] border border-[#D8E4FF] bg-[#F3F7FF] p-6">
        <div className="flex items-center justify-between gap-3"><div className="flex items-center gap-2 text-xs font-bold text-[#2563EB]"><ShieldCheck className="h-4 w-4" />Consent 状态</div><Badge variant="outline" className={consentActive ? "border-[#B9DDD4] text-[#16866D]" : "border-[#E8B8B8] text-[#B73B3B]"}>{booking.consent.status}</Badge></div>
        <p className="mt-4 text-sm leading-7 text-slate-600">范围：{booking.consent.scope.join("、")}。用途仅限服务匹配。</p>
        {consentActive ? <AlertDialog><AlertDialogTrigger asChild><button className="mt-5 flex w-full items-center justify-center gap-2 rounded-full border border-[#BFCDEC] bg-white px-4 py-3 text-sm font-bold text-[#2563EB]"><XCircle className="h-4 w-4" />撤回模拟 Consent</button></AlertDialogTrigger><AlertDialogContent><AlertDialogHeader><AlertDialogTitle>撤回本次服务 Consent？</AlertDialogTitle><AlertDialogDescription>撤回后应停止新的服务处理。预约历史仍保留用于审计，你可以另行取消预约意向。</AlertDialogDescription></AlertDialogHeader><AlertDialogFooter><AlertDialogCancel>暂不撤回</AlertDialogCancel><AlertDialogAction onClick={onWithdraw} className="bg-[#2563EB] text-white">确认撤回</AlertDialogAction></AlertDialogFooter></AlertDialogContent></AlertDialog> : <div className="mt-5 rounded-2xl bg-white p-4 text-xs leading-6 text-slate-500">已撤回。若要继续服务测试，请取消当前意向后重新发起并生成新的 Consent。</div>}
      </aside>
    </div>
  );
}
function Summary({ icon: Icon, label, value }: { icon: typeof CalendarDays; label: string; value: string }) { return <div className="flex gap-3"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-2xl bg-[#EAF1FF] text-[#2563EB]"><Icon className="h-4 w-4" /></span><div><p className="text-xs text-slate-400">{label}</p><strong className="mt-1 block text-sm leading-5">{value}</strong></div></div>; }
