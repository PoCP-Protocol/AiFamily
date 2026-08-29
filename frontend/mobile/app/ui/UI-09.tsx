import { Stack, router, useLocalSearchParams } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { familyApi } from "@/lib/family/family-api-client";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";
import { haptic } from "@/lib/haptics";

interface RemoteTodayAction {
  task_id: string;
  journey_plan_id?: string | null;
  journey_phase?: string | null;
  day_index?: number;
  assignment_text: string;
  task_state: "NOT_STARTED" | "IN_PROGRESS" | "PAUSED" | "CHECKED_IN" | "PARTIAL" | "NOT_COMPLETED" | "CANCELLED";
  execution_status: "NOT_STARTED" | "IN_PROGRESS" | "PAUSED" | "COMPLETED" | "PARTIAL" | "NOT_COMPLETED" | "CANCELLED";
  checkin_allowed: boolean;
  allowed_actions: ("START" | "PAUSE" | "RESUME" | "CANCEL")[];
  task_version: number;
}

interface RemoteTodayProjection { entry_state: "READY" | "EMPTY"; today_task: RemoteTodayAction | null; today_tasks: RemoteTodayAction[] }
interface RemoteTaskReceipt { action: RemoteTodayAction; result_state: "SUCCESS" | "REPLAYED" }

export default function DailyTaskScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const params = useLocalSearchParams<{ campDay?: string }>();
  const requestedCampDay = Number(typeof params.campDay === "string" ? params.campDay : 0);
  const campMode = Number.isInteger(requestedCampDay) && requestedCampDay >= 1 && requestedCampDay <= 21;
  const { todayAction, lastReceipt, activeCampDay, startAction, completeAction, skipAction } = useFamilyMobile();
  const [reflection, setReflection] = useState(lastReceipt?.actionId === todayAction.id ? lastReceipt.reflection : "");
  const [remoteAction, setRemoteAction] = useState<RemoteTodayAction | null>(null);
  const [campActionState, setCampActionState] = useState<"NOT_STARTED" | "IN_PROGRESS" | "CHECKED_IN">("NOT_STARTED");
  const [syncState, setSyncState] = useState<"idle" | "submitting">("idle");
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const retryOperations = useRef<Record<string, { key: string; occurred_at: string }>>({});
  const connected = session.status === "connected" && !!session.token && !!session.selectedFamily;
  const effectiveState = campMode ? campActionState : remoteAction?.task_state ?? (todayAction.status === "checked_in" ? "CHECKED_IN" : todayAction.status === "in_progress" ? "IN_PROGRESS" : "NOT_STARTED");
  const isComplete = ["CHECKED_IN", "PARTIAL", "NOT_COMPLETED"].includes(effectiveState);
  const isStarted = effectiveState === "IN_PROGRESS";
  const isPaused = effectiveState === "PAUSED";
  const isCancelled = effectiveState === "CANCELLED";
  const actionStatusLabel = isComplete ? "已记录" : isStarted ? "进行中" : isPaused ? "已暂停" : isCancelled ? "已取消" : "待开始";
  const actionStatusDetail = isComplete ? "这次行动已经留下过程记录。" : isStarted ? "先完成这一件事，再决定是否记录观察。" : isPaused ? "这项行动可以稍后继续。" : isCancelled ? "今天没有形成完成记录。" : "还没有开始今天的真实任务。";

  const operationFor = (fingerprint: string) => {
    retryOperations.current[fingerprint] ??= { key: `ui09-${fingerprint}-${Date.now().toString(36)}`, occurred_at: new Date().toISOString() };
    return retryOperations.current[fingerprint];
  };

  useEffect(() => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    let active = true;
    familyApi.getFamilyToday<RemoteTodayProjection>(session.token, session.selectedFamily.family_id).then((result) => { if (active) setRemoteAction(result.today_task); }).catch(() => { if (active) setSyncMessage("今天的计划任务暂时无法同步。") });
    return () => { active = false; };
  }, [session.selectedFamily, session.status, session.token]);

  const handlePrimary = async () => {
    if (syncState === "submitting") return;
    if (campMode) {
      if (!isStarted) { setCampActionState("IN_PROGRESS"); haptic.light(); return; }
      setCampActionState("CHECKED_IN"); completeAction(reflection); haptic.success(); return;
    }
    if (connected && session.token && session.selectedFamily) {
      if (!remoteAction?.task_id) { setSyncMessage("当前还没有可执行的计划任务，请回到成长方案后再试。"); return; }
      setSyncState("submitting"); setSyncMessage(null);
      try {
        if (!isStarted) {
          const transition = isPaused ? "RESUME" : "START";
          const operation = operationFor(`${transition.toLowerCase()}-${remoteAction.task_id}-v${remoteAction.task_version}`);
          const receipt = await familyApi.changeTodayTaskState<RemoteTaskReceipt>(session.token, session.selectedFamily.family_id, remoteAction.task_id, { action: transition, occurred_at: operation.occurred_at }, operation.key);
          setRemoteAction(receipt.action); setSyncState("idle"); haptic.light(); return;
        }
        const operation = operationFor(`checkin-${remoteAction.task_id}-v${remoteAction.task_version}`);
        const receipt = await familyApi.checkInTodayTask<RemoteTaskReceipt>(session.token, session.selectedFamily.family_id, remoteAction.task_id, { completion_status: "COMPLETED", reflection, occurred_at: operation.occurred_at }, operation.key);
        setRemoteAction(receipt.action);
      } catch { setSyncState("idle"); setSyncMessage("暂时无法同步这次行动，请稍后重试。"); return; }
      setSyncState("idle");
    } else if (!isStarted) {
      startAction(); haptic.light(); return;
    }
    completeAction(reflection); haptic.success();
  };

  const transitionTask = async (action: "PAUSE" | "CANCEL") => {
    if (!connected || !session.token || !session.selectedFamily || !remoteAction) {
      if (action === "CANCEL") skipAction();
      return;
    }
    const operation = operationFor(`${action.toLowerCase()}-${remoteAction.task_id}-v${remoteAction.task_version}`);
    setSyncState("submitting"); setSyncMessage(null);
    try {
      const receipt = await familyApi.changeTodayTaskState<RemoteTaskReceipt>(session.token, session.selectedFamily.family_id, remoteAction.task_id, { action, occurred_at: operation.occurred_at }, operation.key);
      setRemoteAction(receipt.action); setSyncState("idle"); haptic.selection();
    } catch { setSyncState("idle"); setSyncMessage("状态暂时没有保存，可安全重试。"); }
  };

  const tasks = [
    { id: "1", title: remoteAction?.assignment_text ?? todayAction.title, detail: todayAction.reason, time: `${todayAction.estimatedMinutes}分钟`, checked: isComplete, source: "REAL_TASK" as const },
    { id: "2", title: "记录一次家庭互动", detail: "可选参考，不自动形成任务记录", time: "5分钟", checked: false, source: "REFERENCE" as const },
    { id: "3", title: "做一个专注小游戏", detail: "可选参考，不自动形成任务记录", time: "10分钟", checked: false, source: "REFERENCE" as const },
  ];

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.topBar}><Pressable accessibilityRole="button" accessibilityLabel="返回" onPress={() => router.back()} style={({ pressed }) => [styles.backButton, pressed && styles.pressed]}><IconSymbol name="chevron.left" size={27} color="#24282D" /></Pressable><Text style={styles.topTitle}>今日成长任务</Text><View style={styles.moreCircle}><Text style={styles.moreText}>•••</Text></View></View>
        <View style={styles.reminder}><View style={styles.robot}><Text style={styles.robotFace}>◉‿◉</Text></View><View style={styles.reminderCopy}><Text style={styles.reminderTitle}>AI家庭管家提醒：</Text>{campMode ? <Text style={styles.reminderMain}>今天只练一件小事</Text> : <Text style={styles.reminderMain}>今天先做 <Text style={styles.reminderNumber}>1</Text> 件真实任务</Text>}<Text style={styles.reminderHint}>{campMode ? `21 天成长营 · Day ${requestedCampDay}` : activeCampDay ? `21 天成长营 · Day ${activeCampDay}` : "下方参考只用于启发，不会自动形成任务记录。"}</Text></View></View>
        {remoteAction?.journey_plan_id ? <Text style={styles.planLink}>已关联当前成长计划 · {remoteAction.journey_phase ?? "当前阶段"} · Day {remoteAction.day_index ?? 1}</Text> : null}
        {syncMessage ? <Text style={styles.syncMessage}>{syncMessage}</Text> : null}

        <View style={styles.tasks}>{tasks.map((task) => <TaskCard key={task.id} number={task.id} title={task.title} detail={task.detail} time={task.time} checked={task.checked} source={task.source} />)}</View>
        <View style={styles.actionStatusCard}><View style={styles.actionStatusCopy}><Text style={styles.actionStatusLabel}>今日行动记录</Text><Text style={styles.actionStatusTitle}>{actionStatusLabel}</Text><Text style={styles.actionStatusDetail}>{actionStatusDetail}</Text></View><View style={styles.actionStatusBadge}><IconSymbol name={isComplete ? "checkmark.circle.fill" : "clock.fill"} size={23} color={isComplete ? "#1A8A67" : "#237FEF"} /></View></View>

        {!isComplete && isStarted ? <View style={styles.reflectionPanel}><Text style={[styles.reflectionLabel, { color: colors.text }]}>完成后，记下一句话（可选）</Text><TextInput accessibilityLabel="家长反思" multiline returnKeyType="done" value={reflection} onChangeText={setReflection} placeholder="例如：我先停下来听完了。" placeholderTextColor={colors.muted} style={[styles.input, { color: colors.text, borderColor: colors.border }]} /><Text style={[styles.perspective, { color: colors.muted }]}>这段记录是你的视角，不会被当作孩子的事实或教育结果。</Text></View> : null}

        {isComplete ? <View style={styles.receipt}><IconSymbol name="checkmark.circle.fill" size={25} color="#1A8A67" /><Text style={styles.receiptText}>今天的行动已记录；它不代表已经产生教育效果。</Text></View> : null}
        {isCancelled ? <View style={styles.receipt}><Text style={styles.receiptText}>这项行动已取消，没有形成完成记录或成长结果。</Text></View> : null}
        {!isComplete && !isCancelled ? <Pressable disabled={syncState === "submitting"} onPress={handlePrimary} style={({ pressed }) => [styles.completeButton, (pressed || syncState === "submitting") && styles.pressed]}><Text style={styles.completeText}>{syncState === "submitting" ? "正在同步行动" : isStarted ? "完成今日任务" : isPaused ? "继续今日任务" : "开始今日任务"}</Text></Pressable> : null}
        {isStarted && connected ? <Pressable disabled={syncState === "submitting"} onPress={() => void transitionTask("PAUSE")} style={({ pressed }) => [styles.skipButton, pressed && styles.pressed]}><Text style={[styles.skipText, { color: colors.muted }]}>暂停，稍后继续</Text></Pressable> : null}
        {!campMode && !isComplete && !isCancelled ? <Pressable disabled={syncState === "submitting"} onPress={() => { if (connected) void transitionTask("CANCEL"); else { skipAction(); haptic.selection(); } }} style={({ pressed }) => [styles.skipButton, pressed && styles.pressed]}><Text style={[styles.skipText, { color: colors.muted }]}>今天不适合，取消这项行动</Text></Pressable> : null}
        {campMode && !isComplete ? <Pressable onPress={() => router.back()} style={({ pressed }) => [styles.skipButton, pressed && styles.pressed]}><Text style={[styles.skipText, { color: colors.muted }]}>今天先不练，返回成长营</Text></Pressable> : null}
      </ScrollView>
    </ScreenContainer>
  );
}

function TaskCard({ number, title, detail, time, checked, source }: { number: string; title: string; detail: string; time: string; checked: boolean; source: "REAL_TASK" | "REFERENCE" }) {
  const referenceOnly = source === "REFERENCE";
  return <View style={[styles.taskCard, checked && styles.taskComplete]}><View style={[styles.taskNumber, referenceOnly && styles.referenceNumber]}><Text style={styles.taskNumberText}>{number}</Text></View><View style={styles.taskCopy}><Text style={styles.taskTitle} numberOfLines={1}>{title}</Text><Text style={styles.taskDetail} numberOfLines={1}>{detail}</Text><View style={styles.taskMeta}><Text style={[styles.recordHint, referenceOnly && styles.referenceHint]}>{referenceOnly ? "可选参考" : "真实任务记录"}</Text><Text style={styles.time}>{time}</Text></View></View>{referenceOnly ? <View style={styles.referenceBadge}><Text style={styles.referenceBadgeText}>参考</Text></View> : <View style={[styles.checkbox, checked && styles.checkboxChecked]}>{checked ? <Text style={styles.check}>✓</Text> : null}</View>}</View>;
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 16, paddingBottom: 27, backgroundColor: "#FFFFFF" }, topBar: { minHeight: 61, alignItems: "center", flexDirection: "row", justifyContent: "space-between" }, backButton: { width: 42, height: 42, alignItems: "flex-start", justifyContent: "center" }, topTitle: { color: "#22272D", fontSize: 19, lineHeight: 26, fontWeight: "900" }, moreCircle: { width: 25, height: 25, borderRadius: 13, borderWidth: 2, borderColor: "#2B3036", alignItems: "center", justifyContent: "center" }, moreText: { color: "#2B3036", fontSize: 11, lineHeight: 11, fontWeight: "900", letterSpacing: -1 },
  reminder: { minHeight: 132, borderRadius: 18, paddingHorizontal: 17, backgroundColor: "#E8F2FF", flexDirection: "row", alignItems: "center", overflow: "hidden" }, robot: { width: 80, height: 80, borderRadius: 30, marginRight: 12, backgroundColor: "#FFFFFF", borderWidth: 5, borderColor: "#B9DCFF", justifyContent: "center", alignItems: "center" }, robotFace: { color: "#126EE4", fontSize: 19, lineHeight: 22, fontWeight: "900" }, reminderCopy: { flex: 1, gap: 3 }, reminderTitle: { color: "#5B7091", fontSize: 17, lineHeight: 22, fontWeight: "900" }, reminderMain: { color: "#09295A", fontSize: 18, lineHeight: 25, fontWeight: "900" }, reminderNumber: { color: "#2563EB", fontSize: 28, lineHeight: 30 }, reminderHint: { color: "#536A8B", fontSize: 11, lineHeight: 16, fontWeight: "700" },
  tasks: { gap: 11, marginTop: 13 }, taskCard: { minHeight: 113, paddingHorizontal: 13, paddingVertical: 13, borderRadius: 19, borderWidth: 1.5, borderColor: "#E3EAF2", flexDirection: "row", alignItems: "center", backgroundColor: "#FFFFFF" }, taskComplete: { backgroundColor: "#F2FBF7", borderColor: "#9EDCC4" }, taskNumber: { width: 39, height: 39, borderRadius: 20, backgroundColor: "#2E8BEE", alignItems: "center", justifyContent: "center" }, referenceNumber: { backgroundColor: "#8EA3BA" }, taskNumberText: { color: "#FFFFFF", fontSize: 23, lineHeight: 27, fontWeight: "900" }, taskCopy: { flex: 1, marginLeft: 13, gap: 3 }, taskTitle: { color: "#343940", fontSize: 17, lineHeight: 23, fontWeight: "900" }, taskDetail: { color: "#68727D", fontSize: 12, lineHeight: 18, fontWeight: "700" }, taskMeta: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 2 }, recordHint: { color: "#F29B30", fontSize: 12, lineHeight: 17, fontWeight: "900" }, referenceHint: { color: "#68727D" }, time: { color: "#3A85E8", fontSize: 12, lineHeight: 17, fontWeight: "900" }, checkbox: { width: 30, height: 30, borderRadius: 7, borderWidth: 2, borderColor: "#91BDF4", marginLeft: 8, alignItems: "center", justifyContent: "center" }, checkboxChecked: { backgroundColor: "#2D8CEF", borderColor: "#2D8CEF" }, check: { color: "#FFFFFF", fontSize: 18, lineHeight: 20, fontWeight: "900" }, referenceBadge: { minWidth: 42, minHeight: 28, borderRadius: 14, backgroundColor: "#F1F5F9", alignItems: "center", justifyContent: "center", marginLeft: 8 }, referenceBadgeText: { color: "#68727D", fontSize: 11, lineHeight: 16, fontWeight: "900" },
  actionStatusCard: { minHeight: 104, marginTop: 15, borderRadius: 17, borderWidth: 1.5, borderColor: "#E3EAF2", flexDirection: "row", alignItems: "center", backgroundColor: "#FFFFFF", paddingHorizontal: 17, gap: 12 }, actionStatusCopy: { flex: 1, gap: 4 }, actionStatusLabel: { color: "#3D444C", fontSize: 15, lineHeight: 21, fontWeight: "900" }, actionStatusTitle: { color: "#237FEF", fontSize: 24, lineHeight: 30, fontWeight: "900" }, actionStatusDetail: { color: "#68727D", fontSize: 12, lineHeight: 18, fontWeight: "700" }, actionStatusBadge: { width: 46, height: 46, borderRadius: 17, backgroundColor: "#EAF3FF", alignItems: "center", justifyContent: "center" },
  planLink: { marginTop: 10, color: "#476A92", fontSize: 12, lineHeight: 17, fontWeight: "800" }, syncMessage: { marginTop: 8, color: "#8B6643", fontSize: 12, lineHeight: 17, fontWeight: "700" }, reflectionPanel: { marginTop: 13, gap: 7 }, reflectionLabel: { fontSize: 14, lineHeight: 20, fontWeight: "800" }, input: { minHeight: 89, borderWidth: 1, borderRadius: 14, padding: 12, fontSize: 14, lineHeight: 20, textAlignVertical: "top" }, perspective: { fontSize: 11, lineHeight: 16 }, receipt: { minHeight: 52, marginTop: 13, borderRadius: 13, paddingHorizontal: 12, backgroundColor: "#EEF9F3", flexDirection: "row", alignItems: "center", gap: 8 }, receiptText: { flex: 1, color: "#416A5B", fontSize: 12, lineHeight: 17, fontWeight: "700" }, completeButton: { minHeight: 65, marginTop: 15, borderRadius: 33, backgroundColor: "#187AF2", alignItems: "center", justifyContent: "center" }, completeText: { color: "#FFFFFF", fontSize: 20, lineHeight: 27, fontWeight: "900" }, skipButton: { minHeight: 40, alignItems: "center", justifyContent: "center" }, skipText: { fontSize: 13, lineHeight: 18, fontWeight: "700" }, pressed: { opacity: 0.86, transform: [{ scale: 0.985 }] },
});
