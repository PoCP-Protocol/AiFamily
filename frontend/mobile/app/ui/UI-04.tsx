import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { familyApi } from "@/lib/family/family-api-client";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";
import { MOBILE_JOURNEY_PHASES, type MobileJourneyPhase } from "@/lib/family/journey-plan-content";
import { getUiActionPolicy } from "@/lib/family/ui-action-policies";
import { haptic } from "@/lib/haptics";

interface RemoteJourneyPlan {
  plan?: { plan_id?: string; status?: string; current_phase?: string; phases?: { phase: string; status: string }[] } | null;
}

interface RemotePlanPreview {
  structure?: { stages?: { stage_id: string; small_action: string }[] };
}

interface RemoteGrowthPriority {
  active_priority?: { priority_id?: string } | null;
}

type BaselineWeek = {
  id: MobileJourneyPhase["id"];
  week: string;
  title: string;
  intent: string;
  tasks: readonly [string, string];
  tone: "mint" | "blue" | "orange" | "gray";
  illustration: string;
};

const PLAN_SUMMARY_STATS = [
  { value: "待确认", label: "当前阶段" },
  { value: "0", label: "今日任务" },
  { value: "0h", label: "累计时长" },
  { value: "90天", label: "计划周期" },
] as const;

const BASELINE_WEEKS: readonly BaselineWeek[] = [
  { id: "SEE", week: "第1周", title: "关系破冰", intent: "建立信任，打开沟通通道", tasks: ["亲子时光15分钟", "倾听孩子的感受"], tone: "mint", illustration: "♥" },
  { id: "PARENT_FIRST", week: "第2周", title: "行为训练", intent: "减少冲突，正向引导行为", tasks: ["积极反馈练习", "制定家庭规则"], tone: "blue", illustration: "▣" },
  { id: "CO_CREATE", week: "第3周", title: "习惯建立", intent: "制定计划，培养好习惯", tasks: ["学习计划制定", "每日习惯打卡"], tone: "orange", illustration: "◎" },
  { id: "STABILIZE", week: "第4周", title: "情绪管理", intent: "识别情绪，科学表达", tasks: ["识别此刻的感受", "用一句话表达需要"], tone: "gray", illustration: "○" },
] as const;

function getPhaseStatus(plan: RemoteJourneyPlan["plan"], phaseId: string, currentPhase: string | null) {
  if (!plan?.plan_id || plan.status === "DRAFT") return "pending" as const;
  const remote = plan?.phases?.find((phase) => phase.phase === phaseId)?.status;
  if (remote === "COMPLETED") return "completed" as const;
  if (phaseId === currentPhase) return "active" as const;
  return "pending" as const;
}

export default function JourneyPlanScreen() {
  const session = useFamilyApiSession();
  const { activeOnboardingId, recordUiAction } = useFamilyMobile();
  const [remoteJourney, setRemoteJourney] = useState<RemoteJourneyPlan | null>(null);
  const [remotePreview, setRemotePreview] = useState<RemotePlanPreview | null>(null);
  const [remotePriority, setRemotePriority] = useState<RemoteGrowthPriority | null>(null);
  const [projectionState, setProjectionState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [projectionError, setProjectionError] = useState<string | null>(null);
  const [activationState, setActivationState] = useState<"idle" | "submitting">("idle");
  const [activationMessage, setActivationMessage] = useState<string | null>(null);

  const loadPlanProjection = useCallback(async () => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    setProjectionState("loading"); setProjectionError(null);
    try {
      const [journeyResult, previewResult, priorityResult] = await Promise.all([
        familyApi.getJourneyPlan<RemoteJourneyPlan>(session.token, session.selectedFamily.family_id),
        activeOnboardingId ? familyApi.getPlanPreview<RemotePlanPreview>(session.token, session.selectedFamily.family_id, activeOnboardingId) : Promise.resolve(null),
        activeOnboardingId ? familyApi.getGrowthPriority<RemoteGrowthPriority>(session.token, session.selectedFamily.family_id, activeOnboardingId) : Promise.resolve(null),
      ]);
      setRemoteJourney(journeyResult); setRemotePreview(previewResult); setRemotePriority(priorityResult); setProjectionState("ready");
    } catch { setProjectionState("error"); setProjectionError("成长方案暂时无法同步；请稍后重试。"); }
  }, [activeOnboardingId, session.selectedFamily, session.status, session.token]);

  useEffect(() => { void loadPlanProjection(); }, [loadPlanProjection]);

  const plan = remoteJourney?.plan;
  const currentPhase = plan?.current_phase ?? null;
  const planIsActive = !!plan?.plan_id && plan.status !== "DRAFT";
  const phases = useMemo(() => {
    const remoteStages = remotePreview?.structure?.stages ?? [];
    return BASELINE_WEEKS.map((week, index) => {
      const remote = remoteStages.find((stage) => stage.stage_id === week.id);
      const fallback = MOBILE_JOURNEY_PHASES[index];
      return { ...week, smallAction: remote?.small_action ?? fallback?.smallAction ?? week.tasks[0] };
    });
  }, [remotePreview]);

  const beginPlan = async () => {
    if (activationState === "submitting") return;
    if (session.status !== "connected" || !session.token || !session.selectedFamily) {
      setActivationMessage("请先连接家庭账户，再开始这段成长计划。");
      return;
    }
    if (!activeOnboardingId) {
      setActivationMessage("请先完成家庭测评和成长解读，再开始计划。");
      router.push("/ui/UI-02" as Href);
      return;
    }

    setActivationState("submitting");
    setActivationMessage(null);
    try {
      let currentPlan = plan;
      if (!currentPlan?.plan_id) {
        const priorityId = remotePriority?.active_priority?.priority_id;
        if (!priorityId) throw new Error("GROWTH_PRIORITY_REQUIRED");
        const created = await familyApi.createJourneyPlan<RemoteJourneyPlan>(
          session.token,
          session.selectedFamily.family_id,
          activeOnboardingId,
          priorityId,
          `ui04-create-${activeOnboardingId}`,
        );
        currentPlan = created.plan;
      }
      if (!currentPlan?.plan_id) throw new Error("JOURNEY_PLAN_REQUIRED");
      if (currentPlan.status === "DRAFT") {
        const confirmed = await familyApi.confirmJourneyPlan<RemoteJourneyPlan>(
          session.token,
          session.selectedFamily.family_id,
          currentPlan.plan_id,
          `ui04-confirm-${currentPlan.plan_id}`,
        );
        currentPlan = confirmed.plan;
      }
      setRemoteJourney({ plan: currentPlan });
      const policy = getUiActionPolicy("UI-04");
      if (policy) recordUiAction(policy, "家庭已确认并开始执行当前成长计划");
      haptic.success();
      router.push("/ui/UI-05" as Href);
    } catch (error) {
      const code = error instanceof Error ? error.message : "PLAN_ACTIVATION_FAILED";
      setActivationMessage(code === "GROWTH_PRIORITY_REQUIRED" ? "请先在成长解读中确认当前关注方向。" : "暂时无法开启计划，请稍后重试。");
    } finally {
      setActivationState("idle");
    }
  };

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.screen}>
        <FlatList
          refreshControl={<FamilyRefreshControl />}
          data={phases}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.content}
          ListHeaderComponent={
            <>
              <View style={styles.topBar}>
                <Pressable onPress={() => router.back()} hitSlop={10} style={styles.backButton}>
                  <IconSymbol name="chevron.left" size={27} color="#222222" />
                </Pressable>
                <Text style={styles.topTitle}>90天成长方案</Text>
                <View style={styles.topActions}><Text style={styles.moreText}>•••</Text><Text style={styles.circleText}>⊙</Text></View>
              </View>
              <PlanSummaryCard planIsActive={planIsActive} />
              {projectionState === "error" ? <Pressable onPress={() => void loadPlanProjection()} style={styles.projectionNotice}><Text style={styles.projectionNoticeText}>{projectionError} 点击重试</Text></Pressable> : null}
            </>
          }
          renderItem={({ item, index }) => {
            const status = getPhaseStatus(plan, item.id, currentPhase);
            const tone = toneStyles[item.tone];
            const statusLabel = status === "completed" ? "已完成" : status === "active" ? "进行中" : "未开始";
            return (
              <View style={styles.timelineRow}>
                <View style={styles.timelineRail}>
                  <View style={[styles.timelineDot, { backgroundColor: tone.dot }]} />
                  {index < phases.length - 1 ? <View style={[styles.timelineLine, { backgroundColor: tone.line }]} /> : null}
                </View>
                <View style={[styles.weekCard, { backgroundColor: tone.surface, borderColor: tone.border }]}>
                  <View style={styles.weekHeader}>
                    <View style={[styles.weekBadge, { backgroundColor: tone.badge }]}><Text style={styles.weekBadgeText}>{item.week}</Text></View>
                    <Text style={styles.weekTitle}>{item.title}</Text>
                    <Text style={styles.weekStatus}>（{statusLabel}）</Text>
                  </View>
                  <Text style={styles.weekIntent}>{item.intent}</Text>
                  <View style={styles.weekBody}>
                    <View style={styles.taskList}>
                      {item.tasks.map((task, taskIndex) => {
                        const done = status === "completed" || (status === "active" && taskIndex === 0);
                        return (
                          <View key={task} style={styles.taskLine}>
                            <View style={[styles.taskBullet, { borderColor: tone.dot }]}><View style={[styles.taskBulletInner, { backgroundColor: done ? tone.dot : "transparent" }]} /></View>
                            <Text style={styles.taskText}>{task}</Text>
                            {done ? <IconSymbol name="checkmark.circle.fill" size={18} color={tone.dot} /> : <View style={[styles.emptyCheck, { borderColor: tone.dot }]} />}
                          </View>
                        );
                      })}
                    </View>
                    <View style={[styles.illustration, { backgroundColor: tone.art }]}><Text style={[styles.illustrationText, { color: tone.dot }]}>{item.illustration}</Text></View>
                  </View>
                  {status === "active" ? <Text style={[styles.currentAction, { color: tone.dot }]}>{item.smallAction}</Text> : null}
                </View>
              </View>
            );
          }}
        />
        <View style={styles.fixedFooter}>
          {activationMessage ? <Text style={styles.activationMessage}>{activationMessage}</Text> : null}
          <Pressable disabled={activationState === "submitting"} onPress={beginPlan} style={({ pressed }) => [styles.primaryButton, (pressed || activationState === "submitting") && styles.pressed]}><Text style={styles.primaryButtonText}>{activationState === "submitting" ? "正在开启计划" : "开始执行计划"}</Text></Pressable>
        </View>
      </View>
    </ScreenContainer>
  );
}

function PlanSummaryCard({ planIsActive }: { planIsActive: boolean }) {
  const stats = planIsActive ? [
    { value: "3", label: "当前阶段" },
    { value: "12", label: "今日任务" },
    { value: "36h", label: "累计时长" },
    { value: "90天", label: "计划周期" },
  ] : PLAN_SUMMARY_STATS;
  return (
    <View accessibilityLabel="当前阶段、目标、累计时长、难度与计划统计" style={styles.summaryReference}>
      <View style={styles.summaryGlow} />
      <View style={styles.summaryHeader}>
        <View>
          <Text style={styles.summaryEyebrow}>当前成长阶段</Text>
          <Text style={styles.summaryTitle}>90天成长方案</Text>
        </View>
        <View style={styles.summaryBadge}><Text style={styles.summaryBadgeText}>{planIsActive ? "进行中" : "待确认"}</Text></View>
      </View>
      <Text style={styles.summaryGoal}>目标：建立稳定沟通节奏，完成亲子关系、习惯与情绪三类训练</Text>
      <View style={styles.summaryStatsRow}>
        {stats.map((stat) => (
          <View key={stat.label} style={styles.summaryStat}>
            <Text style={styles.summaryStatValue}>{stat.value}</Text>
            <Text style={styles.summaryStatLabel}>{stat.label}</Text>
          </View>
        ))}
      </View>
      <View style={styles.summaryProgressTrack}><View style={styles.summaryProgressFill} /></View>
      <View style={styles.summaryFooterRow}>
        <Text style={styles.summaryFooterText}>难度：温和进阶</Text>
        <Text style={styles.summaryFooterText}>每周 3-4 次</Text>
      </View>
    </View>
  );
}

const toneStyles = {
  mint: { surface: "#F1FCF7", border: "#CDEFE1", badge: "#19B785", dot: "#18AE76", line: "#90DFC2", art: "#DDF8EB" },
  blue: { surface: "#F0F6FF", border: "#D3E2FF", badge: "#317EED", dot: "#2F81F7", line: "#AFCBF9", art: "#DCEBFF" },
  orange: { surface: "#FFF8EB", border: "#F6E0BC", badge: "#F09C24", dot: "#F5A11E", line: "#F5CEA0", art: "#FFEECE" },
  gray: { surface: "#F7F8FA", border: "#E4E7EC", badge: "#9299A4", dot: "#A6ADB7", line: "#D4D8DE", art: "#EEF0F3" },
} as const;

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#FFFFFF" },
  content: { paddingBottom: 106 },
  topBar: { minHeight: 64, paddingHorizontal: 18, alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  backButton: { width: 36, alignItems: "flex-start" },
  topTitle: { color: "#20242A", fontSize: 19, lineHeight: 26, fontWeight: "800" },
  topActions: { width: 58, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  moreText: { color: "#20242A", fontSize: 17, lineHeight: 19, fontWeight: "900", letterSpacing: 1 },
  circleText: { color: "#20242A", fontSize: 25, lineHeight: 25 },
  summaryReference: { alignSelf: "center", width: "100%", minHeight: 222, marginTop: 2, marginBottom: 5, paddingHorizontal: 20, paddingTop: 18, paddingBottom: 17, borderRadius: 0, backgroundColor: "#FFF4E8", overflow: "hidden" },
  summaryGlow: { position: "absolute", right: -28, top: -35, width: 148, height: 148, borderRadius: 74, backgroundColor: "#FFD7A8", opacity: 0.56 },
  summaryHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  summaryEyebrow: { color: "#B2621D", fontSize: 12, lineHeight: 17, fontWeight: "800" },
  summaryTitle: { color: "#231F20", fontSize: 25, lineHeight: 34, fontWeight: "900", marginTop: 2 },
  summaryBadge: { minHeight: 28, borderRadius: 14, paddingHorizontal: 12, alignItems: "center", justifyContent: "center", backgroundColor: "#FF8A1F" },
  summaryBadgeText: { color: "#FFFFFF", fontSize: 12, lineHeight: 17, fontWeight: "900" },
  summaryGoal: { color: "#6A4A2C", fontSize: 13, lineHeight: 20, fontWeight: "700", marginTop: 11 },
  summaryStatsRow: { flexDirection: "row", gap: 8, marginTop: 17 },
  summaryStat: { flex: 1, minHeight: 58, borderRadius: 14, backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center", shadowColor: "#D88916", shadowOpacity: 0.08, shadowRadius: 8, shadowOffset: { width: 0, height: 3 }, elevation: 1 },
  summaryStatValue: { color: "#FF8A1F", fontSize: 20, lineHeight: 26, fontWeight: "900" },
  summaryStatLabel: { color: "#7A614A", fontSize: 10, lineHeight: 14, fontWeight: "700", marginTop: 2 },
  summaryProgressTrack: { height: 7, borderRadius: 7, backgroundColor: "#F8DEC0", marginTop: 16, overflow: "hidden" },
  summaryProgressFill: { width: "42%", height: 7, borderRadius: 7, backgroundColor: "#FF8A1F" },
  summaryFooterRow: { flexDirection: "row", justifyContent: "space-between", marginTop: 9 },
  summaryFooterText: { color: "#7A614A", fontSize: 11, lineHeight: 16, fontWeight: "700" },
  timelineRow: { flexDirection: "row", paddingHorizontal: 18, minHeight: 164 },
  timelineRail: { width: 28, alignItems: "center" },
  timelineDot: { width: 11, height: 11, borderRadius: 6, marginTop: 17, zIndex: 1 },
  timelineLine: { position: "absolute", top: 28, width: 2, bottom: -3 },
  weekCard: { flex: 1, borderWidth: 1, borderRadius: 12, paddingHorizontal: 14, paddingTop: 13, paddingBottom: 12, marginBottom: 12 },
  weekHeader: { flexDirection: "row", alignItems: "center", gap: 7 },
  weekBadge: { borderRadius: 3, paddingHorizontal: 8, paddingTop: 3, paddingBottom: 3 },
  weekBadgeText: { color: "#FFFFFF", fontSize: 13, lineHeight: 17, fontWeight: "800" },
  weekTitle: { color: "#1D242D", fontSize: 18, lineHeight: 24, fontWeight: "900" },
  weekStatus: { color: "#8D96A3", fontSize: 12, lineHeight: 17 },
  weekIntent: { color: "#4E5B68", fontSize: 14, lineHeight: 21, fontWeight: "600", marginTop: 7 },
  weekBody: { flexDirection: "row", marginTop: 10, gap: 8 },
  taskList: { flex: 1, gap: 8, paddingTop: 2 },
  taskLine: { minHeight: 21, flexDirection: "row", alignItems: "center", gap: 7 },
  taskBullet: { width: 14, height: 14, borderWidth: 1.5, borderRadius: 7, alignItems: "center", justifyContent: "center" },
  taskBulletInner: { width: 6, height: 6, borderRadius: 3 },
  taskText: { flex: 1, color: "#3D4854", fontSize: 13, lineHeight: 18, fontWeight: "600" },
  emptyCheck: { width: 17, height: 17, borderRadius: 9, borderWidth: 1.5 },
  illustration: { width: 70, height: 70, borderRadius: 35, alignItems: "center", justifyContent: "center", alignSelf: "center" },
  illustrationText: { fontSize: 37, lineHeight: 42, fontWeight: "900" },
  currentAction: { fontSize: 12, lineHeight: 18, fontWeight: "700", marginTop: 9 },
  fixedFooter: { position: "absolute", left: 0, right: 0, bottom: 0, backgroundColor: "#FFFFFF", paddingHorizontal: 19, paddingTop: 11, paddingBottom: 13, borderTopWidth: 1, borderTopColor: "#F2F2F2" },
  primaryButton: { minHeight: 54, borderRadius: 27, alignItems: "center", justifyContent: "center", backgroundColor: "#FF8A1F" },
  primaryButtonText: { color: "#FFFFFF", fontSize: 19, lineHeight: 26, fontWeight: "900" },
  projectionNotice: { marginTop: 10, borderRadius: 12, padding: 10, backgroundColor: "#FFF4F0" }, projectionNoticeText: { color: "#9D4E38", fontSize: 11, lineHeight: 16, textAlign: "center", fontWeight: "800" }, activationMessage: { marginHorizontal: 4, marginBottom: 8, color: "#A0532C", fontSize: 12, lineHeight: 18, textAlign: "center" },
  pressed: { opacity: 0.86, transform: [{ scale: 0.985 }] },
});
