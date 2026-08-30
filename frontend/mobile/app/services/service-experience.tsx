import type { Href } from "expo-router";
import { Stack, router, useLocalSearchParams } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { familyApi } from "@/lib/family/family-api-client";
import type { AvailabilitySlotDto } from "@/lib/family/service-api-contracts";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { channelLabel, isServiceAccessDenied, mapServiceOfferings, type ServiceCardModel } from "./service-contract";

export type ServiceExperienceState = "idle" | "loading" | "ready" | "synthetic" | "empty" | "denied" | "error";

const NEEDS = [
  { id: "COMMUNICATION", label: "亲子沟通", prompt: "从一句更容易说出口的话开始" },
  { id: "EMOTION", label: "情绪陪伴", prompt: "先让家庭有一个可以喘气的空间" },
  { id: "STUDY", label: "学习节奏", prompt: "把催促改成一个小而清楚的步骤" },
  { id: "FAMILY", label: "家庭关系", prompt: "让彼此重新靠近一点" },
] as const;

const SYNTHETIC_SERVICES: readonly ServiceCardModel[] = [{
  id: "synthetic-family-support",
  ref: "SYNTHETIC_FAMILY_SUPPORT",
  title: "家庭支持顾问（演示）",
  provider: "家庭支持团队",
  summary: "先听见家庭当前的难处，再一起决定是否需要继续。",
  channel: "文字或视频待确认",
  theme: "COMMUNICATION",
  expertise: ["亲子沟通", "情绪承接", "家庭节奏"],
  provenance: "SYNTHETIC",
  accent: "#16866D",
}];

export default function ServiceOfferingsExperienceScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const [state, setState] = useState<ServiceExperienceState>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [services, setServices] = useState<ServiceCardModel[]>([]);
  const [query, setQuery] = useState("");
  const [need, setNeed] = useState<(typeof NEEDS)[number]["id"] | null>(null);

  useEffect(() => {
    if (session.status === "local_synthetic") {
      setServices([...SYNTHETIC_SERVICES]);
      setState("synthetic");
      setMessage(null);
      return;
    }
    if (session.status !== "connected" || !session.token || !session.selectedFamily) {
      setServices([]);
      setState(session.status === "authentication_required" || session.status === "no_family" ? "denied" : "idle");
      return;
    }
    let active = true;
    setState("loading");
    familyApi.getServiceOfferings(session.token, session.selectedFamily.family_id)
      .then((rows) => {
        if (!active) return;
        const next = mapServiceOfferings(rows);
        setServices(next);
        setState(next.length ? "ready" : "empty");
      })
      .catch((error: unknown) => {
        if (!active) return;
        setServices([]);
        setState(isServiceAccessDenied(error) ? "denied" : "error");
        setMessage(isServiceAccessDenied(error) ? "当前家庭授权或平台策略暂不允许读取服务目录。" : "服务目录暂时没有同步成功，可以稍后再试。");
      });
    return () => {
      active = false;
    };
  }, [session.selectedFamily, session.status, session.token]);

  const filtered = useMemo(() => {
    const value = query.trim().toLowerCase();
    return services.filter((item) => (!value || `${item.title}${item.provider}${item.summary}`.toLowerCase().includes(value)) && (!need || item.theme === need));
  }, [need, query, services]);
  const selectedNeed = NEEDS.find((item) => item.id === need);

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView contentContainerStyle={[styles.content, { backgroundColor: colors.background }]} showsVerticalScrollIndicator={false}>
        <View style={styles.topBar}><Pressable accessibilityRole="button" accessibilityLabel="返回" onPress={() => router.back()} style={styles.back}><IconSymbol name="chevron.left" size={24} color={colors.text} /></Pressable><Text style={[styles.topTitle, { color: colors.text }]}>找一位陪你梳理的人</Text><View style={styles.back} /></View>
        <View style={styles.empathy}><Text style={styles.eyebrow}>We are 伐木累</Text><Text style={styles.heroTitle}>不用一个人扛着，先把难处说给懂的人听</Text><Text style={styles.heroBody}>服务不是评判，也不是替家庭做决定。先接住疲惫，再一起找一个可尝试的小行动。</Text><View style={styles.pathRow}>{(["接住情绪", "了解支持", "确认下一步"] as const).map((label, index) => <View key={label} style={styles.path}><Text style={styles.pathNumber}>{index + 1}</Text><Text style={styles.pathText}>{label}</Text></View>)}</View></View>
        <View style={[styles.needCard, { backgroundColor: colors.surface, borderColor: colors.border }]}><Text style={[styles.sectionTitle, { color: colors.text }]}>现在最想被支持的地方</Text><TextInput accessibilityLabel="服务需要" value={query} onChangeText={setQuery} placeholder="可以输入一个词，或一句话" placeholderTextColor={colors.muted} style={[styles.search, { color: colors.text, borderColor: colors.border }]} /><View style={styles.needRow}>{NEEDS.map((item) => <Pressable key={item.id} accessibilityRole="button" onPress={() => setNeed(need === item.id ? null : item.id)} style={({ pressed }) => [styles.needChip, { borderColor: need === item.id ? colors.tint : colors.border, backgroundColor: need === item.id ? `${colors.tint}12` : colors.background }, pressed && styles.pressed]}><Text style={[styles.needLabel, { color: need === item.id ? colors.tint : colors.text }]}>{item.label}</Text></Pressable>)}</View><Text style={[styles.helper, { color: colors.muted }]}>{selectedNeed ? `你想先从“${selectedNeed.label}”看看：${selectedNeed.prompt}。` : "选择方向只是为了更容易开始，不代表家庭被贴上标签。"}</Text></View>
        {state === "loading" ? <View style={[styles.notice, { backgroundColor: colors.surface, borderColor: colors.border }]}><ActivityIndicator color={colors.tint} /><Text style={[styles.noticeText, { color: colors.muted }]}>正在寻找当前家庭可见的支持……</Text></View> : null}
        {state === "denied" ? <View style={styles.denied}><Text style={styles.noticeTitle}>先保护家庭的选择</Text><Text style={styles.noticeText}>{message ?? "当前不能读取服务目录，不会用其他家庭的数据代替。"}</Text></View> : null}
        {state === "error" ? <View style={styles.error}><Text style={styles.noticeTitle}>服务目录暂时没有回应</Text><Text style={styles.noticeText}>{message}</Text></View> : null}
        {state === "empty" ? <View style={[styles.notice, { backgroundColor: colors.surface, borderColor: colors.border }]}><Text style={[styles.noticeTitle, { color: colors.text }]}>暂时没有匹配的支持</Text><Text style={[styles.noticeText, { color: colors.muted }]}>换一个方向试试，也可以先从产品目录了解方法。</Text><Pressable accessibilityRole="button" onPress={() => router.push("/catalog" as Href)}><Text style={[styles.link, { color: colors.tint }]}>去看支持目录 ›</Text></Pressable></View> : null}
        {state === "synthetic" ? <Text style={[styles.synthetic, { color: colors.muted }]}>当前为本机演示资料；真实环境使用同样的服务流程，不会把演示服务当作真实可预约事实。</Text> : null}
        {filtered.length ? <View style={styles.list}>{filtered.map((item) => <ServiceCard key={item.id} item={item} colors={colors} onOpen={() => router.push({ pathname: "/services/offerings/[offeringRef]", params: { offeringRef: item.ref } } as Href)} />)}</View> : null}
        <View style={styles.next}><Text style={styles.nextTitle}>看中一个方向，也不用马上决定</Text><Text style={styles.nextBody}>可以先生成方案草案；家庭确认前不会预约、扣款、联系服务方或替你做选择。</Text><Pressable accessibilityRole="button" onPress={() => router.push("/journeys/plan" as Href)} style={({ pressed }) => [styles.nextButton, pressed && styles.pressed]}><Text style={styles.nextButtonText}>去看看方案草案 ›</Text></Pressable></View>
        <Text style={[styles.boundary, { color: colors.muted }]}>服务资料按当前家庭、租户、语言与授权范围返回。AI 只生成 Draft/Proposal，不做诊断、不展示家庭总分或排名。</Text>
      </ScrollView>
    </ScreenContainer>
  );
}

function ServiceCard({ item, colors, onOpen }: { item: ServiceCardModel; colors: ReturnType<typeof useColors>; onOpen: () => void }) {
  return <Pressable accessibilityRole="button" accessibilityLabel={`了解${item.title}`} onPress={onOpen} style={({ pressed }) => [styles.card, { backgroundColor: colors.surface, borderColor: colors.border }, pressed && styles.pressed]}><View style={[styles.cardIcon, { backgroundColor: `${item.accent}18` }]}><IconSymbol name="person.2.fill" size={25} color={item.accent} /></View><View style={styles.cardCopy}><View style={styles.cardHeading}><Text style={[styles.cardTitle, { color: colors.text }]} numberOfLines={2}>{item.title}</Text><Text style={[styles.badge, { color: item.provenance === "SYNTHETIC" ? colors.muted : colors.success }]}>{item.provenance === "SYNTHETIC" ? "演示资料" : "服务资料"}</Text></View><Text style={[styles.cardSummary, { color: colors.muted }]}>{item.summary}</Text><Text style={[styles.cardMeta, { color: colors.muted }]}>{item.provider} · {item.channel}</Text><View style={styles.tags}>{item.expertise.slice(0, 3).map((tag) => <Text key={tag} style={[styles.tag, { color: item.accent, borderColor: `${item.accent}55` }]}>{tag}</Text>)}</View><Text style={[styles.cardAction, { color: colors.tint }]}>先了解边界，再决定是否继续 ›</Text></View></Pressable>;
}

export function ServiceOfferingDetailExperienceScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const { offeringRef } = useLocalSearchParams<{ offeringRef?: string }>();
  const [state, setState] = useState<ServiceExperienceState>("idle");
  const [offering, setOffering] = useState<ServiceCardModel | null>(null);
  const [slots, setSlots] = useState<AvailabilitySlotDto[]>([]);
  const [selectedSlot, setSelectedSlot] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (session.status === "local_synthetic") {
      setOffering(SYNTHETIC_SERVICES[0]);
      setSlots([]);
      setState("synthetic");
      return;
    }
    if (session.status !== "connected" || !session.token || !session.selectedFamily) {
      setState(session.status === "authentication_required" || session.status === "no_family" ? "denied" : "idle");
      return;
    }
    let active = true;
    setState("loading");
    familyApi.getServiceOfferings(session.token, session.selectedFamily.family_id)
      .then(async (rows) => {
        const found = rows.find((item) => item.service_offering_ref === offeringRef);
        if (!active) return;
        if (!found) {
          setState("empty");
          setMessage("这个支持方向暂时不在当前家庭可见目录中。");
          return;
        }
        setOffering(mapServiceOfferings([found])[0] ?? null);
        const nextSlots = await familyApi.getServiceSlots(session.token!, session.selectedFamily!.family_id, found.service_offering_id);
        if (!active) return;
        setSlots(nextSlots);
        setSelectedSlot(nextSlots.find((item) => item.status === "OPEN")?.availability_slot_ref ?? null);
        setState("ready");
      })
      .catch((error: unknown) => {
        if (!active) return;
        setState(isServiceAccessDenied(error) ? "denied" : "error");
        setMessage(isServiceAccessDenied(error) ? "当前家庭授权或平台策略暂不允许读取这个服务。" : "服务详情暂时没有同步成功，可以稍后再试。");
      });
    return () => {
      active = false;
    };
  }, [offeringRef, session.selectedFamily, session.status, session.token]);

  return <ScreenContainer edges={["left", "right", "bottom"]}><Stack.Screen options={{ headerShown: false }} /><ScrollView contentContainerStyle={[styles.content, { backgroundColor: colors.background }]}><View style={styles.topBar}><Pressable accessibilityRole="button" accessibilityLabel="返回" onPress={() => router.back()} style={styles.back}><IconSymbol name="chevron.left" size={24} color={colors.text} /></Pressable><Text style={[styles.topTitle, { color: colors.text }]}>支持详情</Text><View style={styles.back} /></View>{state === "loading" ? <View style={[styles.notice, { backgroundColor: colors.surface, borderColor: colors.border }]}><ActivityIndicator color={colors.tint} /><Text style={[styles.noticeText, { color: colors.muted }]}>正在读取服务边界与可用安排……</Text></View> : null}{state === "denied" || state === "error" || state === "empty" ? <View style={state === "denied" ? styles.denied : styles.error}><Text style={styles.noticeTitle}>{state === "denied" ? "先保护家庭的选择" : state === "empty" ? "暂时找不到这个支持" : "服务详情暂时没有回应"}</Text><Text style={styles.noticeText}>{message}</Text><Pressable accessibilityRole="button" onPress={() => router.push("/services/offerings" as Href)}><Text style={styles.link}>回到服务目录 ›</Text></Pressable></View> : null}{offering ? <><View style={[styles.detailHero, { backgroundColor: `${offering.accent}15` }]}><View style={[styles.detailIcon, { backgroundColor: `${offering.accent}28` }]}><IconSymbol name="person.2.fill" size={34} color={offering.accent} /></View><Text style={[styles.badge, { color: offering.accent }]}>{offering.provenance === "SYNTHETIC" ? "本机演示资料" : "当前家庭可见"}</Text><Text style={[styles.detailTitle, { color: colors.text }]}>{offering.title}</Text><Text style={[styles.detailSub, { color: colors.muted }]}>{offering.provider} · {offering.channel}</Text></View><View style={[styles.section, { backgroundColor: colors.surface, borderColor: colors.border }]}><Text style={[styles.sectionTitle, { color: colors.text }]}>先照顾家庭的感受</Text><Text style={[styles.body, { color: colors.muted }]}>不需要把问题一次讲清楚。服务方会先听见你在意的部分，再由家庭决定要不要继续。</Text></View><View style={[styles.section, { backgroundColor: colors.surface, borderColor: colors.border }]}><Text style={[styles.sectionTitle, { color: colors.text }]}>可了解的安排</Text>{slots.length ? slots.map((slot) => <Pressable key={slot.availability_slot_ref} accessibilityRole="button" onPress={() => setSelectedSlot(slot.availability_slot_ref)} style={[styles.slot, { borderColor: slot.availability_slot_ref === selectedSlot ? colors.tint : colors.border, backgroundColor: slot.availability_slot_ref === selectedSlot ? `${colors.tint}12` : colors.background }]}><Text style={[styles.slotText, { color: colors.text }]}>{formatSlot(slot.starts_at)} · {channelLabel(slot.channel)}</Text><Text style={[styles.slotMeta, { color: colors.muted }]}>{slot.status === "OPEN" ? `剩余 ${slot.remaining_capacity} 个家庭可了解` : "暂不可选择"}</Text></Pressable>) : <Text style={[styles.body, { color: colors.muted }]}>时间与方式待确认；可以先保存需求，不会占用名额。</Text>}</View><View style={styles.next}><Text style={styles.nextTitle}>把它放进方案草案</Text><Text style={styles.nextBody}>保存意向不会预约或联系服务方；确认后才进入下一步行动。</Text><Pressable accessibilityRole="button" onPress={() => router.push({ pathname: "/services/bookings/new", params: { offeringRef: offering.ref, slotRef: selectedSlot ?? "" } } as Href)} style={({ pressed }) => [styles.nextButton, pressed && styles.pressed]}><Text style={styles.nextButtonText}>保存一个咨询意向 ›</Text></Pressable></View></> : null}<Text style={[styles.boundary, { color: colors.muted }]}>服务资料、可用时段和授权由服务端返回；AI 只作 Draft/Proposal，不作诊断、不比较家庭。</Text></ScrollView></ScreenContainer>;
}

function formatSlot(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "时间待确认" : date.toLocaleString("zh-CN", { month: "numeric", day: "numeric", weekday: "short", hour: "2-digit", minute: "2-digit" });
}

const styles = StyleSheet.create({
  content: { padding: 16, paddingTop: 10, paddingBottom: 40, gap: 14 },
  topBar: { minHeight: 44, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  back: { width: 40, minHeight: 40, justifyContent: "center" },
  topTitle: { fontSize: 20, lineHeight: 28, fontWeight: "900" },
  empathy: { borderRadius: 24, padding: 19, gap: 8, backgroundColor: "#E8F7F1" },
  eyebrow: { color: "#16866D", fontSize: 11, lineHeight: 16, fontWeight: "900" },
  heroTitle: { color: "#0B4F42", fontSize: 24, lineHeight: 32, fontWeight: "900" },
  heroBody: { color: "#4F746B", fontSize: 13, lineHeight: 20 },
  pathRow: { flexDirection: "row", gap: 8, marginTop: 3 },
  path: { flex: 1, minHeight: 42, borderRadius: 14, backgroundColor: "#FFFFFFAA", padding: 7, flexDirection: "row", alignItems: "center", gap: 5 },
  pathNumber: { width: 22, height: 22, borderRadius: 11, backgroundColor: "#16866D", color: "#FFFFFF", textAlign: "center", lineHeight: 22, fontSize: 11, fontWeight: "900" },
  pathText: { flex: 1, color: "#0B4F42", fontSize: 10, lineHeight: 14, fontWeight: "800" },
  needCard: { borderWidth: 1, borderRadius: 20, padding: 15, gap: 10 },
  sectionTitle: { fontSize: 17, lineHeight: 24, fontWeight: "900" },
  search: { minHeight: 47, borderWidth: 1, borderRadius: 14, paddingHorizontal: 12, fontSize: 13, lineHeight: 19 },
  needRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  needChip: { minHeight: 38, borderWidth: 1, borderRadius: 19, paddingHorizontal: 13, justifyContent: "center" },
  needLabel: { fontSize: 12, lineHeight: 17, fontWeight: "800" },
  helper: { fontSize: 11, lineHeight: 17 },
  notice: { minHeight: 63, borderWidth: 1, borderRadius: 17, padding: 13, flexDirection: "row", alignItems: "center", gap: 9 },
  denied: { minHeight: 86, borderWidth: 1, borderColor: "#E9C98B", borderRadius: 17, padding: 14, backgroundColor: "#FFF7E8", gap: 6 },
  error: { minHeight: 86, borderWidth: 1, borderColor: "#F2B5A7", borderRadius: 17, padding: 14, backgroundColor: "#FFF0ED", gap: 6 },
  noticeTitle: { color: "#7D4F00", fontSize: 14, lineHeight: 19, fontWeight: "900" },
  noticeText: { fontSize: 11, lineHeight: 17 },
  link: { color: "#2563EB", fontSize: 12, lineHeight: 17, fontWeight: "900" },
  synthetic: { fontSize: 10, lineHeight: 15, textAlign: "center" },
  list: { gap: 10 },
  card: { minHeight: 136, borderWidth: 1, borderRadius: 19, padding: 13, flexDirection: "row", gap: 10 },
  cardIcon: { width: 49, height: 49, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  cardCopy: { flex: 1, gap: 4 },
  cardHeading: { flexDirection: "row", alignItems: "flex-start", gap: 7 },
  cardTitle: { flex: 1, fontSize: 15, lineHeight: 20, fontWeight: "900" },
  badge: { fontSize: 10, lineHeight: 15, fontWeight: "900" },
  cardSummary: { fontSize: 11, lineHeight: 17 },
  cardMeta: { fontSize: 10, lineHeight: 15 },
  tags: { flexDirection: "row", flexWrap: "wrap", gap: 5 },
  tag: { borderWidth: 1, borderRadius: 8, paddingHorizontal: 6, paddingVertical: 2, fontSize: 9, lineHeight: 13 },
  cardAction: { fontSize: 11, lineHeight: 16, fontWeight: "900" },
  next: { borderWidth: 1, borderRadius: 20, padding: 16, borderColor: "#F3D4A0", backgroundColor: "#FFF5E7", gap: 8 },
  nextTitle: { color: "#7D4F00", fontSize: 17, lineHeight: 23, fontWeight: "900" },
  nextBody: { color: "#8A6B39", fontSize: 12, lineHeight: 18 },
  nextButton: { minHeight: 46, borderRadius: 17, backgroundColor: "#F5D99B", alignItems: "center", justifyContent: "center" },
  nextButtonText: { color: "#7D4F00", fontSize: 13, lineHeight: 18, fontWeight: "900" },
  detailHero: { borderRadius: 24, padding: 19, gap: 8 },
  detailIcon: { width: 70, height: 70, borderRadius: 23, alignItems: "center", justifyContent: "center" },
  detailTitle: { fontSize: 25, lineHeight: 33, fontWeight: "900" },
  detailSub: { fontSize: 12, lineHeight: 18 },
  section: { borderWidth: 1, borderRadius: 19, padding: 15, gap: 10 },
  body: { fontSize: 12, lineHeight: 19 },
  slot: { minHeight: 57, borderWidth: 1, borderRadius: 15, padding: 11, gap: 2 },
  slotText: { fontSize: 12, lineHeight: 18, fontWeight: "800" },
  slotMeta: { fontSize: 10, lineHeight: 15 },
  boundary: { fontSize: 10, lineHeight: 16, textAlign: "center" },
  pressed: { opacity: 0.82, transform: [{ scale: 0.985 }] },
});
