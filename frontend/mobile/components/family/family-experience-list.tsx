import { router } from "expo-router";
import { ActivityIndicator, FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { getScreensForTab, type FamilyTab, type FamilyScreenDefinition } from "@/lib/family/ui-registry";
import { routeForUi } from "@/lib/navigation/family-routes";

export type FamilyExperienceListState = "loading" | "ready" | "empty" | "error" | "paused";

export interface FamilyExperienceListProps {
  tab: FamilyTab;
  eyebrow: string;
  title: string;
  description: string;
  state?: FamilyExperienceListState;
  errorMessage?: string;
  onRetry?: () => void;
}

interface ServiceExperienceMeta {
  icon: "person.crop.circle.fill" | "book.fill" | "calendar.fill" | "headphones.fill" | "message.fill" | "checkmark.seal.fill";
  stage: string;
  accent: string;
  invitation: string;
}

const SERVICE_META: Record<string, ServiceExperienceMeta> = {
  "UI-19": { icon: "person.crop.circle.fill", stage: "认识支持", accent: "#2563EB", invitation: "先看看谁能陪你梳理" },
  "UI-20": { icon: "book.fill", stage: "了解边界", accent: "#7556C8", invitation: "先知道会怎么一起做" },
  "UI-21": { icon: "message.fill", stage: "说出需要", accent: "#F28C45", invitation: "留下一份家庭私有草稿" },
  "UI-22": { icon: "calendar.fill", stage: "探索活动", accent: "#16866D", invitation: "找一个轻松参与的主题" },
  "UI-23": { icon: "book.fill", stage: "选择方式", accent: "#D84D83", invitation: "看看议程，再决定是否继续" },
  "UI-24": { icon: "headphones.fill", stage: "回看安排", accent: "#2563EB", invitation: "把已记下的过程重新看见" },
  "UI-31": { icon: "checkmark.seal.fill", stage: "继续同行", accent: "#F28C45", invitation: "从下一件小事接着走" },
  "UI-34": { icon: "book.fill", stage: "记录成长", accent: "#16866D", invitation: "只记录发生过的过程" },
};

const DEFAULT_META: ServiceExperienceMeta = { icon: "person.crop.circle.fill", stage: "家庭支持", accent: "#2563EB", invitation: "先了解，再决定" };

export function serviceExperienceMeta(screen: FamilyScreenDefinition): ServiceExperienceMeta {
  return SERVICE_META[screen.id] ?? DEFAULT_META;
}

export function FamilyExperienceList({ tab, eyebrow, title, description, state = "ready", errorMessage, onRetry }: FamilyExperienceListProps) {
  const colors = useColors();
  const screens = getScreensForTab(tab);
  const isReady = state === "ready";
  const isPaused = state === "paused";

  return (
    <ScreenContainer>
      <FlatList
        data={isReady || state === "paused" || state === "error" ? screens : []}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.content}
        ListHeaderComponent={<View style={styles.header}><Text style={[styles.eyebrow, { color: colors.tint }]}>{eyebrow}</Text><Text style={[styles.title, { color: colors.text }]}>{title}</Text><Text style={[styles.description, { color: colors.muted }]}>{description}</Text><View style={[styles.empathyCard, { backgroundColor: "#E8F2FF" }]}><Text style={styles.empathyEyebrow}>We are 伐木累 · We are family</Text><Text style={styles.empathyTitle}>先接住疲惫，再一起走一小步</Text><Text style={styles.empathyBody}>服务不是考核，也不是比较。你可以随时暂停、跳过或回来继续，家庭的节奏由家庭决定。</Text><View style={styles.pathRow}>{(["说出需要", "找到支持", "留下回看"] as const).map((label, index) => <View key={label} style={styles.pathItem}><Text style={styles.pathNumber}>{index + 1}</Text><Text style={styles.pathLabel}>{label}</Text></View>)}</View></View>{state === "loading" ? <View style={[styles.notice, { backgroundColor: colors.surface, borderColor: colors.border }]}><ActivityIndicator color={colors.tint} /><Text style={[styles.noticeText, { color: colors.muted }]}>正在把家庭需要和支持方向对上……</Text></View> : null}{state === "error" ? <View style={styles.errorNotice}><Text style={styles.noticeTitle}>服务入口暂时没有回应</Text><Text style={styles.noticeText}>{errorMessage ?? "可以稍后再试，家庭不会因此产生外部影响。"}</Text>{onRetry ? <Pressable accessibilityRole="button" onPress={onRetry} style={styles.retryButton}><Text style={styles.retryText}>重新试试</Text></Pressable> : null}</View> : null}{isPaused ? <View style={styles.pausedNotice}><Text style={styles.noticeTitle}>这段同行已暂停</Text><Text style={styles.noticeText}>不必勉强自己，准备好时再从一小步开始。</Text></View> : null}</View>}
        ListEmptyComponent={state === "empty" ? <View style={[styles.empty, { backgroundColor: colors.surface, borderColor: colors.border }]}><IconSymbol name="heart.fill" size={29} color={colors.muted} /><Text style={[styles.emptyTitle, { color: colors.text }]}>这里还没有可见的支持方向</Text><Text style={[styles.emptyText, { color: colors.muted }]}>可以先说说家庭现在的需要，或稍后再回来看看。</Text></View> : null}
        renderItem={({ item, index }) => <ExperienceRow screen={item} step={index + 1} colors={colors} disabled={state === "loading" || isPaused} />}
        ListFooterComponent={<View style={styles.footer}><View style={[styles.achievement, { backgroundColor: colors.surface, borderColor: colors.border }]}><View style={styles.achievementIcon}><IconSymbol name="star.fill" size={22} color="#F28C45" /></View><View style={styles.achievementCopy}><Text style={[styles.achievementTitle, { color: colors.text }]}>家庭小成就</Text><Text style={[styles.achievementText, { color: colors.muted }]}>完成一次了解、记录或回看，就是在为家庭留下一点力量。只和自己的节奏比。</Text></View></View><Text style={[styles.boundary, { color: colors.muted }]}>服务入口只展示当前家庭有权了解的内容。内部流程编号不会作为用户界面文案，不展示家庭总分、排名或横向比较。</Text></View>}
      />
    </ScreenContainer>
  );
}

function ExperienceRow({ screen, step, colors, disabled }: { screen: FamilyScreenDefinition; step: number; colors: ReturnType<typeof useColors>; disabled: boolean }) {
  const meta = serviceExperienceMeta(screen);
  return <Pressable accessibilityRole="button" accessibilityLabel={`${screen.title}，${meta.invitation}`} disabled={disabled} onPress={() => router.push(routeForUi(screen.id))} style={({ pressed }) => [styles.row, { backgroundColor: colors.surface, borderColor: colors.border }, disabled && styles.disabled, pressed && styles.pressed]}><View style={[styles.iconBubble, { backgroundColor: `${meta.accent}18` }]}><IconSymbol name={meta.icon} size={27} color={meta.accent} /></View><View style={styles.rowCopy}><View style={styles.rowHeading}><Text style={[styles.stepBadge, { color: meta.accent, backgroundColor: `${meta.accent}12` }]}>第 {step} 步 · {meta.stage}</Text><IconSymbol name="chevron.right" size={19} color={colors.muted} /></View><Text style={[styles.rowTitle, { color: colors.text }]}>{screen.title}</Text><Text style={[styles.rowSubtitle, { color: colors.muted }]} numberOfLines={2}>{meta.invitation} · {screen.subtitle}</Text><View style={styles.rowProgress}><View style={[styles.progressDot, { backgroundColor: meta.accent }]} /><Text style={[styles.rowProgressText, { color: colors.muted }]}>完成这一步，下一步会更清楚</Text></View></View></Pressable>;
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 20, paddingTop: 18, paddingBottom: 30, gap: 12 },
  header: { gap: 8, marginBottom: 4 },
  eyebrow: { fontSize: 13, lineHeight: 18, fontWeight: "700", letterSpacing: 1 },
  title: { fontSize: 30, lineHeight: 38, fontWeight: "800" },
  description: { fontSize: 16, lineHeight: 24, maxWidth: 520 },
  empathyCard: { borderRadius: 23, padding: 17, gap: 7, marginTop: 8 },
  empathyEyebrow: { color: "#2563EB", fontSize: 11, lineHeight: 16, fontWeight: "900" },
  empathyTitle: { color: "#09295A", fontSize: 21, lineHeight: 28, fontWeight: "900" },
  empathyBody: { color: "#4D6382", fontSize: 12, lineHeight: 18 },
  pathRow: { flexDirection: "row", gap: 7, marginTop: 3 },
  pathItem: { flex: 1, minHeight: 39, borderRadius: 13, backgroundColor: "#FFFFFFAA", paddingHorizontal: 7, flexDirection: "row", alignItems: "center", gap: 5 },
  pathNumber: { width: 21, height: 21, borderRadius: 11, backgroundColor: "#2563EB", color: "#FFFFFF", textAlign: "center", lineHeight: 21, fontSize: 10, fontWeight: "900" },
  pathLabel: { flex: 1, color: "#09295A", fontSize: 10, lineHeight: 14, fontWeight: "800" },
  notice: { minHeight: 59, borderRadius: 16, borderWidth: 1, padding: 13, flexDirection: "row", alignItems: "center", gap: 9 },
  errorNotice: { minHeight: 88, borderRadius: 16, borderWidth: 1, borderColor: "#F2B5A7", backgroundColor: "#FFF0ED", padding: 13, gap: 6 },
  pausedNotice: { minHeight: 77, borderRadius: 16, borderWidth: 1, borderColor: "#BFD1F8", backgroundColor: "#F1F5FF", padding: 13, gap: 5 },
  noticeTitle: { color: "#7D4F00", fontSize: 13, lineHeight: 18, fontWeight: "900" },
  noticeText: { flex: 1, color: "#6B7890", fontSize: 11, lineHeight: 17 },
  retryButton: { alignSelf: "flex-start", minHeight: 35, borderRadius: 17, paddingHorizontal: 13, backgroundColor: "#F5D99B", justifyContent: "center" },
  retryText: { color: "#7D4F00", fontSize: 11, lineHeight: 16, fontWeight: "900" },
  row: { minHeight: 118, borderWidth: 1, borderRadius: 20, padding: 14, flexDirection: "row", alignItems: "flex-start", gap: 12 },
  iconBubble: { width: 52, height: 52, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  rowCopy: { flex: 1, gap: 4 },
  rowHeading: { minHeight: 22, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 6 },
  stepBadge: { alignSelf: "flex-start", borderRadius: 8, paddingHorizontal: 7, paddingVertical: 3, fontSize: 10, lineHeight: 14, fontWeight: "900" },
  rowTitle: { fontSize: 17, lineHeight: 23, fontWeight: "900" },
  rowSubtitle: { fontSize: 12, lineHeight: 18 },
  rowProgress: { minHeight: 19, flexDirection: "row", alignItems: "center", gap: 6, marginTop: 2 },
  progressDot: { width: 8, height: 8, borderRadius: 4 },
  rowProgressText: { fontSize: 10, lineHeight: 15 },
  empty: { minHeight: 142, borderWidth: 1, borderRadius: 20, padding: 18, alignItems: "center", justifyContent: "center", gap: 6 },
  emptyTitle: { fontSize: 15, lineHeight: 21, fontWeight: "900" },
  emptyText: { fontSize: 12, lineHeight: 18, textAlign: "center" },
  footer: { gap: 13, paddingTop: 5 },
  achievement: { minHeight: 81, borderWidth: 1, borderRadius: 19, padding: 13, flexDirection: "row", alignItems: "center", gap: 10 },
  achievementIcon: { width: 43, height: 43, borderRadius: 15, backgroundColor: "#FFF0D2", alignItems: "center", justifyContent: "center" },
  achievementCopy: { flex: 1, gap: 3 },
  achievementTitle: { fontSize: 14, lineHeight: 19, fontWeight: "900" },
  achievementText: { fontSize: 11, lineHeight: 17 },
  boundary: { fontSize: 10, lineHeight: 16, textAlign: "center" },
  disabled: { opacity: 0.6 },
  pressed: { opacity: 0.8, transform: [{ scale: 0.985 }] },
});
