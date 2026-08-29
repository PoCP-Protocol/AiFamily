import type { Href } from "expo-router";
import { Stack, router, useLocalSearchParams } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { familyApi } from "@/lib/family/family-api-client";
import type { FamilyApiServiceSlotsProjection, FamilyApiServiceSupplyProjection } from "@/lib/family/family-api-projections";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { channelLabel, serviceOfferingsForDisplay } from "@/lib/family/service-support";

export default function TeacherDetailScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const { offeringRef } = useLocalSearchParams<{ offeringRef?: string }>();
  const [projection, setProjection] = useState<FamilyApiServiceSupplyProjection | null>(null);
  const [slots, setSlots] = useState<FamilyApiServiceSlotsProjection | null>(null);
  const [selectedSlot, setSelectedSlot] = useState<string | null>(null);

  useEffect(() => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    let active = true;
    familyApi.getServiceOfferings<FamilyApiServiceSupplyProjection>(session.token, session.selectedFamily.family_id, {})
      .then(async (result) => {
        if (!active) return;
        setProjection(result);
        const selected = result.offerings.find((item) => item.service_offering_ref === offeringRef) ?? result.offerings[0];
        if (!selected) return;
        const slotResult = await familyApi.getServiceSlots<FamilyApiServiceSlotsProjection>(session.token!, session.selectedFamily!.family_id, selected.service_offering_ref, selected.version_no);
        if (!active) return;
        setSlots(slotResult);
        setSelectedSlot(slotResult.slots.find((item) => item.status === "AVAILABLE")?.availability_slot_ref ?? null);
      }).catch((error) => { console.error("UI-20 remote projection failed", error); });
    return () => { active = false; };
  }, [offeringRef, session.selectedFamily, session.status, session.token]);

  const offerings = useMemo(() => serviceOfferingsForDisplay(projection?.offerings), [projection?.offerings]);
  const offering = offerings.find((item) => item.offeringRef === offeringRef) ?? offerings[0];
  const slotRows = slots?.slots ?? [];

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <FlatList
        refreshControl={<FamilyRefreshControl />}
        data={slotRows}
        keyExtractor={(item) => item.availability_slot_ref}
        horizontal={false}
        contentContainerStyle={styles.content}
        ListHeaderComponent={
          <View style={styles.header}>
            <View style={styles.topBar}><Pressable onPress={() => router.back()} style={styles.topBack}><IconSymbol name="chevron.left" size={26} color="#22272D" /></Pressable><Text style={styles.topTitle}>名师详情</Text><IconSymbol name="ellipsis" size={22} color="#22272D" /></View>
            <View style={styles.hero}>
              <View style={styles.heroCopy}>
                <View style={styles.nameRow}><Text style={styles.name}>{offering.providerName}</Text><Text style={styles.dataBadge}>服务资料</Text></View>
                <Text style={styles.role}>{offering.title}</Text>
                <Text style={styles.role}>{offering.ageBand}</Text>
                <View style={styles.heroTags}>{offering.expertise.slice(0, 3).map((tag) => <Text key={tag} style={styles.heroTag}>{tag}</Text>)}</View>
              </View>
              <View style={styles.portrait}><Text style={styles.portraitText}>{offering.providerName.slice(0, 1)}</Text></View>
            </View>

            <View style={[styles.summaryRow, { backgroundColor: colors.surface, borderColor: colors.border }]}>
              <SummaryCell label="家庭可见" value="已准入" color="#E49B18" />
              <SummaryCell label="支持方式" value={channelLabel(offering.channel)} color="#2563EB" />
              <SummaryCell label="当前安排" value={offering.availability === "AVAILABLE" ? "可了解" : "待确认"} color="#16866D" />
            </View>

            <View style={[styles.section, { backgroundColor: colors.surface, borderColor: colors.border }]}>
              <Text style={[styles.sectionTitle, { color: colors.text }]}>老师介绍</Text>
              <Text style={[styles.sectionText, { color: colors.muted }]}>{offering.introduction}</Text>
              <Text style={[styles.boundary, { color: colors.muted }]}>服务资料帮助家庭了解支持方向，不是对家庭或孩子的诊断，也不替代家庭决定。</Text>
            </View>

            <View style={[styles.section, { backgroundColor: colors.surface, borderColor: colors.border }]}>
              <Text style={[styles.sectionTitle, { color: colors.text }]}>擅长领域</Text>
              <View style={styles.expertiseGrid}>{[...offering.expertise, "家庭节奏", "家长支持"].map((tag) => <Text key={tag} style={[styles.expertiseTag, { color: offering.accent, backgroundColor: `${offering.accent}12` }]}>{tag}</Text>)}</View>
            </View>

            <View style={styles.sectionHeading}><Text style={[styles.sectionTitle, { color: colors.text }]}>可了解的时间</Text><Text style={[styles.sectionMeta, { color: colors.muted }]}>{slotRows.length ? "选择一个偏好" : "后续再确认"}</Text></View>
          </View>
        }
        renderItem={({ item }) => {
          const selected = selectedSlot === item.availability_slot_ref;
          const time = formatSlotTime(item.starts_at);
          return <Pressable onPress={() => setSelectedSlot(item.availability_slot_ref)} style={({ pressed }) => [styles.slotCard, { backgroundColor: colors.surface, borderColor: selected ? colors.tint : colors.border }, pressed && styles.pressed]}><View><Text style={[styles.slotDate, { color: colors.text }]}>{time.date}</Text><Text style={[styles.slotTime, { color: selected ? colors.tint : colors.muted }]}>{time.time} · {channelLabel(item.channel)}</Text></View>{selected ? <IconSymbol name="checkmark.circle.fill" size={22} color={colors.tint} /> : null}</Pressable>;
        }}
        ListEmptyComponent={<View style={[styles.emptySlot, { backgroundColor: colors.surface, borderColor: colors.border }]}><IconSymbol name="calendar.fill" size={24} color={colors.muted} /><View style={styles.emptySlotCopy}><Text style={[styles.slotDate, { color: colors.text }]}>暂无可选时段</Text><Text style={[styles.slotTime, { color: colors.muted }]}>仍可先准备咨询需求，具体安排稍后确认。</Text></View></View>}
        ListFooterComponent={
          <View style={styles.footer}>
            <View style={[styles.review, { backgroundColor: "#FFF9EE", borderColor: "#F0D8A5" }]}><Text style={styles.reviewLabel}>家庭体验说明</Text><Text style={[styles.reviewText, { color: colors.muted }]}>先听清家庭需要，再一起讨论可尝试的行动；过程记录不代表教育结果。</Text></View>
            <View style={styles.actionRow}>
              <Pressable onPress={() => router.back()} style={({ pressed }) => [styles.textAction, { borderColor: colors.border }, pressed && styles.pressed]}><IconSymbol name="message.fill" size={20} color={colors.tint} /><Text style={[styles.textActionLabel, { color: colors.tint }]}>在线咨询</Text></Pressable>
              <Pressable onPress={() => router.push(`/ui/UI-21?offeringRef=${encodeURIComponent(offering.offeringRef)}&slotRef=${encodeURIComponent(selectedSlot ?? "")}` as Href)} style={({ pressed }) => [styles.bookAction, pressed && styles.pressed]}><Text style={styles.bookActionLabel}>预约 1 对 1</Text></Pressable>
            </View>
          </View>
        }
      />
    </ScreenContainer>
  );
}

function SummaryCell({ label, value, color }: { label: string; value: string; color: string }) {
  const colors = useColors();
  return <View style={styles.summaryCell}><Text style={[styles.summaryValue, { color }]}>{value}</Text><Text style={[styles.summaryLabel, { color: colors.muted }]}>{label}</Text></View>;
}

function formatSlotTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return { date: "时间待确认", time: "稍后安排" };
  return { date: date.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric", weekday: "short" }), time: date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }) };
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 34, gap: 10 }, header: { gap: 13, marginBottom: 2 },
  topBar: { minHeight: 44, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, topBack: { width: 38, height: 38, alignItems: "flex-start", justifyContent: "center" }, topTitle: { color: "#22272D", fontSize: 19, lineHeight: 26, fontWeight: "900" },
  hero: { minHeight: 190, borderRadius: 25, backgroundColor: "#E8F2FF", padding: 20, flexDirection: "row", alignItems: "center", overflow: "hidden" }, heroCopy: { flex: 1, gap: 6 }, nameRow: { flexDirection: "row", alignItems: "center", gap: 7 },
  name: { color: "#09295A", fontSize: 29, lineHeight: 37, fontWeight: "900" }, dataBadge: { color: "#8A5A00", backgroundColor: "#FFE3A3", borderRadius: 9, paddingHorizontal: 7, paddingVertical: 3, fontSize: 10, lineHeight: 14, fontWeight: "900" }, role: { color: "#5B7091", fontSize: 13, lineHeight: 18, fontWeight: "700" },
  heroTags: { flexDirection: "row", flexWrap: "wrap", gap: 5, marginTop: 5 }, heroTag: { color: "#536A8B", backgroundColor: "#FFFFFF80", borderRadius: 9, paddingHorizontal: 7, paddingVertical: 4, fontSize: 9, lineHeight: 13, fontWeight: "700" },
  portrait: { width: 94, height: 120, borderRadius: 34, backgroundColor: "#F5D3C2", alignItems: "center", justifyContent: "center", alignSelf: "flex-end" }, portraitText: { color: "#09295A", fontSize: 38, fontWeight: "900" },
  summaryRow: { minHeight: 86, borderWidth: 1, borderRadius: 19, flexDirection: "row", alignItems: "center" }, summaryCell: { flex: 1, alignItems: "center", gap: 3, borderRightWidth: StyleSheet.hairlineWidth, borderRightColor: "#D9E0EA" }, summaryValue: { fontSize: 16, lineHeight: 22, fontWeight: "900" }, summaryLabel: { fontSize: 10, lineHeight: 14 },
  section: { borderWidth: 1, borderRadius: 19, padding: 15, gap: 8 }, sectionTitle: { fontSize: 18, lineHeight: 24, fontWeight: "900" }, sectionText: { fontSize: 13, lineHeight: 21 }, boundary: { fontSize: 11, lineHeight: 17 },
  expertiseGrid: { flexDirection: "row", flexWrap: "wrap", gap: 7 }, expertiseTag: { borderRadius: 11, paddingHorizontal: 10, paddingVertical: 6, fontSize: 11, lineHeight: 16, fontWeight: "800" }, sectionHeading: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" }, sectionMeta: { fontSize: 11, lineHeight: 16 },
  slotCard: { minHeight: 68, borderWidth: 1, borderRadius: 17, paddingHorizontal: 14, paddingVertical: 10, flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }, slotDate: { fontSize: 14, lineHeight: 20, fontWeight: "900" }, slotTime: { fontSize: 11, lineHeight: 16, marginTop: 2 },
  emptySlot: { minHeight: 76, borderWidth: 1, borderRadius: 17, padding: 13, flexDirection: "row", alignItems: "center", gap: 10 }, emptySlotCopy: { flex: 1 },
  footer: { gap: 13, marginTop: 4 }, review: { minHeight: 78, borderWidth: 1, borderRadius: 17, padding: 13, gap: 4 }, reviewLabel: { color: "#B87500", fontSize: 11, lineHeight: 16, fontWeight: "900" }, reviewText: { fontSize: 11, lineHeight: 17 }, actionRow: { flexDirection: "row", gap: 9 },
  textAction: { width: 108, minHeight: 52, borderWidth: 1, borderRadius: 18, alignItems: "center", justifyContent: "center", flexDirection: "row", gap: 5 }, textActionLabel: { fontSize: 11, lineHeight: 16, fontWeight: "800" }, bookAction: { flex: 1, minHeight: 52, borderRadius: 18, backgroundColor: "#F28C45", alignItems: "center", justifyContent: "center" }, bookActionLabel: { color: "#FFFFFF", fontSize: 15, lineHeight: 21, fontWeight: "900" }, pressed: { opacity: 0.82, transform: [{ scale: 0.98 }] },
});
