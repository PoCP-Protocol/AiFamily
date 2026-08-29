import type { Href } from "expo-router";
import { Stack, router, useLocalSearchParams } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { familyApi } from "@/lib/family/family-api-client";
import type { FamilyApiServiceBookingReceipt, FamilyApiServiceSlotsProjection, FamilyApiServiceSupplyProjection } from "@/lib/family/family-api-projections";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";
import { channelLabel, serviceOfferingsForDisplay, type ConsultationChannel } from "@/lib/family/service-support";
import { haptic } from "@/lib/haptics";

const CHANNELS: readonly { id: ConsultationChannel; label: string; detail: string; icon: "video.fill" | "message.fill" | "mappin.circle.fill" }[] = [
  { id: "TEXT", label: "文字咨询", detail: "随时整理，按需回复", icon: "message.fill" },
  { id: "VIDEO", label: "视频咨询", detail: "面对面交流，更深入", icon: "video.fill" },
  { id: "OFFLINE", label: "线下咨询", detail: "时间地点另行确认", icon: "mappin.circle.fill" },
] as const;

const AGE_BANDS = ["3–6 岁", "7–9 岁", "10–12 岁", "13 岁以上"] as const;

export default function ConsultationBookingScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const state = useFamilyMobile();
  const { offeringRef, slotRef } = useLocalSearchParams<{ offeringRef?: string; slotRef?: string }>();
  const [supply, setSupply] = useState<FamilyApiServiceSupplyProjection | null>(null);
  const [slots, setSlots] = useState<FamilyApiServiceSlotsProjection | null>(null);
  const [channel, setChannel] = useState<ConsultationChannel>("VIDEO");
  const [selectedSlot, setSelectedSlot] = useState<string | null>(slotRef || null);
  const [ageBand, setAgeBand] = useState<(typeof AGE_BANDS)[number]>("7–9 岁");
  const [needFocus, setNeedFocus] = useState("");
  const [expectation, setExpectation] = useState("");
  const [submitState, setSubmitState] = useState<"idle" | "submitting" | "saved" | "error">("idle");

  useEffect(() => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    let active = true;
    familyApi.getServiceOfferings<FamilyApiServiceSupplyProjection>(session.token, session.selectedFamily.family_id, {})
      .then(async (result) => {
        if (!active) return;
        setSupply(result);
        const selected = result.offerings.find((item) => item.service_offering_ref === offeringRef) ?? result.offerings[0];
        if (!selected) return;
        const slotResult = await familyApi.getServiceSlots<FamilyApiServiceSlotsProjection>(session.token!, session.selectedFamily!.family_id, selected.service_offering_ref, selected.version_no);
        if (!active) return;
        setSlots(slotResult);
        const preferred = slotResult.slots.find((item) => item.availability_slot_ref === slotRef) ?? slotResult.slots.find((item) => item.status === "AVAILABLE");
        setSelectedSlot(preferred?.availability_slot_ref ?? null);
        if (preferred) setChannel(preferred.channel);
      }).catch((error) => { console.error("UI-21 remote action failed", error); });
    return () => { active = false; };
  }, [offeringRef, session.selectedFamily, session.status, session.token, slotRef]);

  const offerings = useMemo(() => serviceOfferingsForDisplay(supply?.offerings), [supply?.offerings]);
  const offering = offerings.find((item) => item.offeringRef === offeringRef) ?? offerings[0];
  const selectedSlotModel = slots?.slots.find((item) => item.availability_slot_ref === selectedSlot) ?? null;
  const timePreference = selectedSlotModel ? formatSlot(selectedSlotModel.starts_at) : "具体时间稍后确认";

  const saveConsultationNeed = async () => {
    const familyPerspective = needFocus.trim() || "想先了解家庭当前最需要支持的方向";
    if (!offering) { setSubmitState("error"); return; }
    const flowId = `consultation:${offering.offeringRef}`;
    state.setFlowStatus({ flowId, lastAction: "SAVE_CONSULTATION_NEED_DRAFT", remoteSyncState: "NOT_STARTED", source: "LOCAL_DRAFT", retryable: false });
    state.saveConsultationNeedDraft(offering.offeringRef, offering.version, offering.title, offering.providerName, channel, selectedSlot, timePreference, ageBand, familyPerspective);
    setSubmitState("submitting");
    if (session.status !== "connected" || !session.token || !session.selectedFamily || !selectedSlot) {
      setSubmitState("saved");
      haptic.success();
      return;
    }
    try {
      state.setFlowStatus({ flowId, lastAction: "SUBMIT_SERVICE_BOOKING", remoteSyncState: "SYNCING", source: "LOCAL_DRAFT", retryable: false });
      const result = await familyApi.submitServiceBooking<FamilyApiServiceBookingReceipt>(
        session.token,
        session.selectedFamily.family_id,
        {
          page_id: "UI-21",
          service_offering_ref: offering.offeringRef,
          service_offering_version: offering.version,
          availability_slot_ref: selectedSlot,
          attributes: { entry: "family_ai_mobile_consultation_need", channel_preference: channel },
        },
        `family-mobile-ui21:${session.selectedFamily.family_id}:${offering.offeringRef}:${selectedSlot}`,
      );
      state.syncConsultationNeedReceipt(result.booking.booking_request_id, result.service_record.service_record_id);
      state.setFlowStatus({ flowId, lastAction: "SUBMIT_SERVICE_BOOKING", remoteSyncState: "SYNCED", source: "REMOTE_RECEIPT", retryable: false });
      setSubmitState("saved");
      haptic.success();
    } catch {
      state.setFlowStatus({ flowId, lastAction: "SUBMIT_SERVICE_BOOKING", remoteSyncState: "ERROR", source: "LOCAL_DRAFT", retryable: true });
      setSubmitState("error");
    }
  };

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.topBar}><Pressable onPress={() => router.back()} style={styles.topBack}><IconSymbol name="chevron.left" size={26} color="#22272D" /></Pressable><Text style={styles.topTitle}>在线咨询 / 预约</Text><Text style={styles.topMore}>↗</Text></View>
        <View style={styles.steps}>
          {["选择方式", "选择时间", "填写信息", "确认需求"].map((label, index) => <View key={label} style={styles.step}><View style={[styles.stepCircle, { backgroundColor: index === 0 ? colors.tint : colors.surface, borderColor: index === 0 ? colors.tint : colors.border }]}><Text style={[styles.stepNumber, { color: index === 0 ? "#FFFFFF" : colors.muted }]}>{index + 1}</Text></View><Text style={[styles.stepLabel, { color: index === 0 ? colors.text : colors.muted }]}>{label}</Text></View>)}
        </View>

        <Text style={[styles.sectionTitle, { color: colors.text }]}>选择咨询方式</Text>
        <View style={styles.channelGrid}>{CHANNELS.map((item) => <Pressable key={item.id} onPress={() => setChannel(item.id)} style={({ pressed }) => [styles.channelCard, { backgroundColor: colors.surface, borderColor: channel === item.id ? colors.tint : colors.border }, pressed && styles.pressed]}><View style={[styles.channelIcon, { backgroundColor: channel === item.id ? "#2563EB18" : "#8794A515" }]}><IconSymbol name={item.icon} size={24} color={channel === item.id ? colors.tint : colors.muted} /></View><View style={styles.channelCopy}><Text style={[styles.channelLabel, { color: colors.text }]}>{item.label}</Text><Text style={[styles.channelDetail, { color: colors.muted }]}>{item.detail}</Text></View></Pressable>)}</View>

        <View style={styles.sectionHeading}><Text style={[styles.sectionTitle, { color: colors.text }]}>选择时间</Text><Text style={[styles.sectionMeta, { color: colors.muted }]}>也可以稍后确认</Text></View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.slotRow}>
          {(slots?.slots ?? []).map((item) => { const selected = selectedSlot === item.availability_slot_ref; return <Pressable key={item.availability_slot_ref} onPress={() => { setSelectedSlot(item.availability_slot_ref); setChannel(item.channel); }} style={({ pressed }) => [styles.slotChip, { backgroundColor: selected ? "#EAF1FF" : colors.surface, borderColor: selected ? colors.tint : colors.border }, pressed && styles.pressed]}><Text style={[styles.slotText, { color: selected ? colors.tint : colors.text }]}>{formatSlot(item.starts_at)}</Text><Text style={[styles.slotChannel, { color: colors.muted }]}>{channelLabel(item.channel)}</Text></Pressable>; })}
          {!slots?.slots.length ? <View style={[styles.slotChip, { backgroundColor: colors.surface, borderColor: colors.border }]}><Text style={[styles.slotText, { color: colors.text }]}>时间待确认</Text><Text style={[styles.slotChannel, { color: colors.muted }]}>先保存家庭偏好</Text></View> : null}
        </ScrollView>

        <Text style={[styles.sectionTitle, { color: colors.text }]}>家庭需求</Text>
        <View style={[styles.formCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <Text style={[styles.fieldLabel, { color: colors.text }]}>孩子年龄阶段</Text>
          <View style={styles.ageRow}>{AGE_BANDS.map((item) => <Pressable key={item} onPress={() => setAgeBand(item)} style={({ pressed }) => [styles.ageChip, { borderColor: ageBand === item ? colors.tint : colors.border, backgroundColor: ageBand === item ? "#EAF1FF" : colors.background }, pressed && styles.pressed]}><Text style={[styles.ageText, { color: ageBand === item ? colors.tint : colors.muted }]}>{item}</Text></Pressable>)}</View>
          <Text style={[styles.fieldLabel, { color: colors.text }]}>想先了解的问题</Text>
          <TextInput value={needFocus} onChangeText={setNeedFocus} multiline maxLength={180} placeholder="例如：最近写作业容易分心，沟通时双方都很着急" placeholderTextColor={colors.muted} style={[styles.textArea, { color: colors.text, borderColor: colors.border, backgroundColor: colors.background }]} textAlignVertical="top" />
          <Text style={[styles.perspectiveHint, { color: colors.muted }]}>这里记录的是家长当前的观察和感受，不会被当作对孩子的事实或诊断。</Text>
          <Text style={[styles.fieldLabel, { color: colors.text }]}>希望先获得什么帮助</Text>
          <TextInput value={expectation} onChangeText={setExpectation} multiline maxLength={120} placeholder="例如：先找到一个今晚可以尝试的小步骤" placeholderTextColor={colors.muted} style={[styles.textAreaSmall, { color: colors.text, borderColor: colors.border, backgroundColor: colors.background }]} textAlignVertical="top" />
        </View>

        <View style={[styles.consent, { backgroundColor: "#F2F7FF", borderColor: "#CADBFA" }]}><IconSymbol name="checkmark.circle.fill" size={21} color={colors.tint} /><Text style={[styles.consentText, { color: colors.muted }]}>我理解这只是保存咨询需求；是否安排真人服务、具体时间和方式，之后仍需家庭确认。</Text></View>

        {submitState === "saved" || state.consultationNeedDraft?.offeringRef === offering.offeringRef ? <View style={[styles.receipt, { backgroundColor: "#16866D12", borderColor: colors.success }]}><IconSymbol name="checkmark.circle.fill" size={24} color={colors.success} /><View style={styles.receiptCopy}><Text style={[styles.receiptTitle, { color: colors.success }]}>咨询需求已记下</Text><Text style={[styles.receiptText, { color: colors.muted }]}>当前没有向外部联系人发消息；你可以在“我的咨询与活动”里回看。</Text></View></View> : submitState === "error" ? <Text style={[styles.error, { color: colors.error }]}>暂时无法同步，但本机的家庭私有草稿已经保留。</Text> : null}

        <Pressable disabled={submitState === "submitting"} onPress={saveConsultationNeed} style={({ pressed }) => [styles.confirmAction, { backgroundColor: colors.tint }, pressed && styles.pressed, submitState === "submitting" && styles.disabled]}>{submitState === "submitting" ? <View style={styles.loadingContent}><ActivityIndicator size="small" color="#FFFFFF" /><Text style={styles.confirmText}>正在保存</Text></View> : <Text style={styles.confirmText}>确认预约</Text>}</Pressable>
        <Pressable onPress={() => router.push("/ui/UI-24" as Href)} style={({ pressed }) => [styles.recordsAction, pressed && styles.pressed]}><Text style={[styles.recordsText, { color: colors.tint }]}>查看我的咨询与活动</Text><IconSymbol name="chevron.right" size={18} color={colors.tint} /></Pressable>
        <Modal transparent visible={submitState === "saved"} animationType="fade" onRequestClose={() => setSubmitState("idle")}><View style={styles.modalScrim}><View style={styles.successModal}><IconSymbol name="checkmark.circle.fill" size={44} color={colors.success} /><Text style={styles.successTitle}>咨询需求已保存</Text><Text style={styles.successText}>已记录在家庭私有空间。当前没有联系专家、确认时段或发送通知。</Text><Pressable onPress={() => setSubmitState("idle")} style={styles.successAction}><Text style={styles.successActionText}>我知道了</Text></Pressable></View></View></Modal>
      </ScrollView>
    </ScreenContainer>
  );
}

function formatSlot(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "时间待确认";
  return `${date.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric", weekday: "short" })} ${date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}`;
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 17, paddingTop: 12, paddingBottom: 38, gap: 14 }, topBar: { minHeight: 42, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, topBack: { width: 38, height: 38, alignItems: "flex-start", justifyContent: "center" }, topTitle: { color: "#22272D", fontSize: 19, lineHeight: 26, fontWeight: "900" }, topMore: { color: "#22272D", fontSize: 22, lineHeight: 26 }, steps: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }, step: { width: "24%", alignItems: "center", gap: 5 }, stepCircle: { width: 28, height: 28, borderRadius: 14, borderWidth: 1, alignItems: "center", justifyContent: "center" }, stepNumber: { fontSize: 11, fontWeight: "900" }, stepLabel: { fontSize: 9, lineHeight: 13, fontWeight: "700", textAlign: "center" },
  sectionTitle: { fontSize: 19, lineHeight: 26, fontWeight: "900" }, sectionHeading: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" }, sectionMeta: { fontSize: 11, lineHeight: 16 }, channelGrid: { flexDirection: "row", flexWrap: "wrap", gap: 9 }, channelCard: { width: "48%", minHeight: 88, borderWidth: 1, borderRadius: 17, padding: 11, flexDirection: "row", alignItems: "center", gap: 8 }, channelIcon: { width: 40, height: 40, borderRadius: 13, alignItems: "center", justifyContent: "center" }, channelCopy: { flex: 1, gap: 2 }, channelLabel: { fontSize: 13, lineHeight: 18, fontWeight: "900" }, channelDetail: { fontSize: 9, lineHeight: 14 },
  slotRow: { gap: 8 }, slotChip: { minWidth: 128, minHeight: 62, borderWidth: 1, borderRadius: 15, paddingHorizontal: 12, paddingVertical: 9, gap: 2 }, slotText: { fontSize: 11, lineHeight: 16, fontWeight: "900" }, slotChannel: { fontSize: 9, lineHeight: 13 },
  formCard: { borderWidth: 1, borderRadius: 20, padding: 14, gap: 10 }, fieldLabel: { fontSize: 13, lineHeight: 18, fontWeight: "900" }, ageRow: { flexDirection: "row", flexWrap: "wrap", gap: 7 }, ageChip: { borderWidth: 1, borderRadius: 12, paddingHorizontal: 9, paddingVertical: 6 }, ageText: { fontSize: 10, lineHeight: 15, fontWeight: "800" }, textArea: { minHeight: 94, borderWidth: 1, borderRadius: 14, padding: 11, fontSize: 13, lineHeight: 20 }, textAreaSmall: { minHeight: 72, borderWidth: 1, borderRadius: 14, padding: 11, fontSize: 13, lineHeight: 20 }, perspectiveHint: { fontSize: 10, lineHeight: 16 },
  consent: { minHeight: 70, borderWidth: 1, borderRadius: 17, padding: 12, flexDirection: "row", alignItems: "flex-start", gap: 8 }, consentText: { flex: 1, fontSize: 11, lineHeight: 17 }, receipt: { minHeight: 80, borderWidth: 1, borderRadius: 18, padding: 13, flexDirection: "row", alignItems: "center", gap: 9 }, receiptCopy: { flex: 1, gap: 3 }, receiptTitle: { fontSize: 14, lineHeight: 20, fontWeight: "900" }, receiptText: { fontSize: 11, lineHeight: 17 }, error: { fontSize: 12, lineHeight: 18 },
  confirmAction: { minHeight: 54, borderRadius: 18, alignItems: "center", justifyContent: "center" }, loadingContent: { flexDirection: "row", alignItems: "center", gap: 8 }, disabled: { opacity: 0.78 }, confirmText: { color: "#FFFFFF", fontSize: 16, lineHeight: 22, fontWeight: "900" }, recordsAction: { minHeight: 42, alignItems: "center", justifyContent: "center", flexDirection: "row", gap: 2 }, recordsText: { fontSize: 12, lineHeight: 17, fontWeight: "800" }, modalScrim: { flex: 1, backgroundColor: "#09295A66", alignItems: "center", justifyContent: "center", paddingHorizontal: 34 }, successModal: { width: "100%", borderRadius: 24, backgroundColor: "#FFFFFF", padding: 24, alignItems: "center", gap: 12 }, successTitle: { color: "#09295A", fontSize: 20, lineHeight: 28, fontWeight: "900" }, successText: { color: "#5D6D84", fontSize: 13, lineHeight: 20, textAlign: "center" }, successAction: { alignSelf: "stretch", minHeight: 48, borderRadius: 18, backgroundColor: "#2563EB", alignItems: "center", justifyContent: "center", marginTop: 4 }, successActionText: { color: "#FFFFFF", fontSize: 15, lineHeight: 21, fontWeight: "900" }, pressed: { opacity: 0.82, transform: [{ scale: 0.98 }] },
});
