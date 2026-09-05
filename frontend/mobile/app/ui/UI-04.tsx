import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { createMobileRequestId, familyApi } from "@/lib/family/family-api-client";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import {
  isAdoptedGrowthPlan,
  isGrowthPlanDraft,
  isGrowthPlanInformationNeeded,
  type AdoptedGenerativeGrowthPlan,
  type GenerativeGrowthPlanDraft,
  type GenerativeGrowthPlanResponse,
  type GrowthPlanStage,
} from "@/lib/family/generative-growth-plan";
import { haptic } from "@/lib/haptics";

type LoadState = "idle" | "loading" | "ready" | "empty" | "error";
const actorLabel = { ADULT: "家长", FAMILY: "全家", CHILD_OPTIONAL: "孩子自愿参与" } as const;

export default function GenerativeGrowthPlanScreen() {
  const session = useFamilyApiSession();
  const [response, setResponse] = useState<GenerativeGrowthPlanResponse | null>(null);
  const [loadState, setLoadState] = useState<LoadState>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [selectedChoices, setSelectedChoices] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  const loadPlan = useCallback(async () => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) {
      setLoadState("empty");
      return;
    }
    setLoadState("loading");
    setMessage(null);
    try {
      const result = await familyApi.getGenerativeGrowthPlan<GenerativeGrowthPlanResponse>(
        session.token,
        session.selectedFamily.family_id,
      );
      setResponse(result);
      if (isAdoptedGrowthPlan(result.plan)) {
        setSelectedChoices(result.plan.selected_choices);
      }
      setLoadState(result.plan ? "ready" : "empty");
    } catch {
      setResponse(null);
      setLoadState("error");
      setMessage("成长方案暂时没有同步成功。你的家庭理解仍会保留，可以稍后再试。");
    }
  }, [session.selectedFamily, session.status, session.token]);

  useEffect(() => { void loadPlan(); }, [loadPlan]);

  const plan = response?.plan ?? null;
  const draft = isGrowthPlanDraft(plan) ? plan : null;
  const adoptedPlan = isAdoptedGrowthPlan(plan) ? plan : null;
  const informationNeeded = isGrowthPlanInformationNeeded(plan) ? plan : null;
  const allChoicesSelected = useMemo(
    () => !draft || draft.adjustable_choices.every((choice) => selectedChoices[choice.choice_id]),
    [draft, selectedChoices],
  );

  const adoptPlan = async () => {
    if (!draft || submitting || !allChoicesSelected) return;
    if (session.status !== "connected" || !session.token || !session.selectedFamily) {
      setMessage("请先连接你的家庭账户，再保存这份方案。");
      return;
    }
    setSubmitting(true);
    setMessage(null);
    try {
      const adopted = await familyApi.adoptGenerativeGrowthPlan<GenerativeGrowthPlanResponse>(
        session.token,
        session.selectedFamily.family_id,
        {
          draft_ref: draft.draft_ref,
          draft_version: draft.draft_version,
          selected_choices: selectedChoices,
        },
        createMobileRequestId("ui04-adopt"),
      );
      setResponse(adopted);
      haptic.success();
      setMessage("方案已按你的选择保存。接下来会从今天最合适的支持开始。");
    } catch {
      setMessage("这次没有保存成功，请检查方案是否已更新后再试。");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.screen}>
        <Header />
        <ScrollView refreshControl={<FamilyRefreshControl />} contentContainerStyle={styles.content}>
          {loadState === "loading" ? <LoadingState /> : null}
          {loadState === "empty" ? <EmptyState /> : null}
          {loadState === "error" ? <ErrorState message={message} onRetry={loadPlan} /> : null}
          {informationNeeded ? (
            <InformationNeeded
              summary={informationNeeded.known_context_summary}
              questions={informationNeeded.information_needed}
              limitations={informationNeeded.limitations}
            />
          ) : null}
          {draft || adoptedPlan ? (
            <PlanDraft
              draft={draft ?? adoptedPlan!}
              adopted={Boolean(adoptedPlan)}
              selectedChoices={selectedChoices}
              onSelect={(choiceId, option) => setSelectedChoices((current) => ({ ...current, [choiceId]: option }))}
            />
          ) : null}
          {message && loadState === "ready" ? <Text style={styles.message}>{message}</Text> : null}
        </ScrollView>
        {adoptedPlan ? (
          <View style={styles.footer}>
            <Pressable onPress={() => router.push("/" as Href)} style={styles.secondaryButton}>
              <Text style={styles.secondaryButtonText}>返回首页</Text>
            </Pressable>
            <Pressable onPress={() => router.push("/ui/UI-05" as Href)} style={styles.primaryButton}>
              <Text style={styles.primaryButtonText}>进入成长陪伴</Text>
            </Pressable>
          </View>
        ) : draft ? (
          <View style={styles.footer}>
            <Pressable onPress={() => router.push("/ui/UI-02" as Href)} style={styles.secondaryButton}>
              <Text style={styles.secondaryButtonText}>返回调整理解</Text>
            </Pressable>
            <Pressable
              disabled={!allChoicesSelected || submitting}
              onPress={adoptPlan}
              style={[styles.primaryButton, (!allChoicesSelected || submitting) && styles.disabledButton]}
            >
              <Text style={styles.primaryButtonText}>{submitting ? "正在保存" : "按我的选择采用"}</Text>
            </Pressable>
          </View>
        ) : null}
      </View>
    </ScreenContainer>
  );
}

function Header() {
  return (
    <View style={styles.header}>
      <Pressable onPress={() => router.back()} hitSlop={10} style={styles.iconButton}>
        <IconSymbol name="chevron.left" size={25} color="#2A251F" />
      </Pressable>
      <View style={styles.headerTitleWrap}>
        <Text style={styles.headerEyebrow}>与你共同完成</Text>
        <Text style={styles.headerTitle}>家庭成长方案</Text>
      </View>
      <View style={styles.iconButton} />
    </View>
  );
}

function LoadingState() {
  return (
    <View style={styles.centerState}>
      <ActivityIndicator color="#D66A2C" size="large" />
      <Text style={styles.stateTitle}>正在结合家庭理解与专业知识</Text>
      <Text style={styles.stateCopy}>AI会先判断信息是否足够，再组织一份可以共同修改的方案。</Text>
    </View>
  );
}

function EmptyState() {
  return (
    <View style={styles.centerState}>
      <View style={styles.stateOrb}><Text style={styles.stateOrbText}>AI</Text></View>
      <Text style={styles.stateTitle}>先让AI真正理解你们</Text>
      <Text style={styles.stateCopy}>说说最近最想改变的一件事。可以是一次冲突、一段语音，也可以是一张让你在意的照片。</Text>
      <Pressable onPress={() => router.push("/ui/UI-02" as Href)} style={styles.stateAction}>
        <Text style={styles.stateActionText}>开始家庭理解</Text>
      </Pressable>
    </View>
  );
}

function ErrorState({ message, onRetry }: { message: string | null; onRetry: () => Promise<void> }) {
  return (
    <View style={styles.centerState}>
      <Text style={styles.stateTitle}>方案还没有准备好</Text>
      <Text style={styles.stateCopy}>{message}</Text>
      <Pressable onPress={() => void onRetry()} style={styles.stateAction}><Text style={styles.stateActionText}>重新同步</Text></Pressable>
    </View>
  );
}

function InformationNeeded({ summary, questions, limitations }: { summary: string; questions: string[]; limitations: string[] }) {
  return (
    <View>
      <Hero kicker="AI目前的理解" title="还需要听你多说一点" copy={summary} />
      <Text style={styles.sectionTitle}>补充这些信息，方案会更贴近你们</Text>
      {questions.map((question, index) => (
        <View key={question} style={styles.questionCard}>
          <Text style={styles.questionIndex}>{String(index + 1).padStart(2, "0")}</Text>
          <Text style={styles.questionText}>{question}</Text>
        </View>
      ))}
      {limitations.length ? <Text style={styles.limitationText}>当前仍不确定：{limitations.join("；")}</Text> : null}
      <Pressable onPress={() => router.push("/ui/UI-02" as Href)} style={styles.stateAction}><Text style={styles.stateActionText}>继续和AI聊聊</Text></Pressable>
    </View>
  );
}

function Hero({ kicker, title, copy }: { kicker: string; title: string; copy: string }) {
  return (
    <View style={styles.heroCard}>
      <Text style={styles.heroKicker}>{kicker}</Text>
      <Text style={styles.heroTitle}>{title}</Text>
      <Text style={styles.heroCopy}>{copy}</Text>
    </View>
  );
}

function PlanDraft({ draft, adopted, selectedChoices, onSelect }: {
  draft: GenerativeGrowthPlanDraft | AdoptedGenerativeGrowthPlan;
  adopted: boolean;
  selectedChoices: Record<string, string>;
  onSelect: (choiceId: string, option: string) => void;
}) {
  return (
    <View>
      <View style={styles.heroCard}>
        <View style={styles.heroTopRow}>
          <Text style={styles.heroKicker}>基于你确认的家庭理解</Text>
          <View style={styles.draftBadge}><Text style={styles.draftBadgeText}>{adopted ? "已采用" : "待你决定"}</Text></View>
        </View>
        <Text style={styles.heroTitle}>{draft.title}</Text>
        <Text style={styles.heroCopy}>{draft.family_goal.statement}</Text>
        <View style={styles.durationRow}>
          <Text style={styles.durationValue}>{draft.duration.days}</Text>
          <Text style={styles.durationUnit}>天建议周期</Text>
          <Text style={styles.durationReason}>{draft.duration.rationale}</Text>
        </View>
      </View>
      <View style={styles.reasonCard}>
        <Text style={styles.reasonLabel}>为什么这样安排</Text>
        <Text style={styles.reasonText}>{draft.why_this_plan}</Text>
      </View>
      <Text style={styles.sectionTitle}>我们建议这样推进</Text>
      {draft.stages.map((stage, index) => <StageCard key={stage.stage_id} stage={stage} index={index} />)}
      <Text style={styles.sectionTitle}>{adopted ? "你们确认的节奏" : "把方案调成你们家的节奏"}</Text>
      {draft.adjustable_choices.map((choice) => (
        <View key={choice.choice_id} style={styles.choiceCard}>
          <Text style={styles.choiceQuestion}>{choice.question}</Text>
          <View style={styles.choiceOptions}>
            {choice.options.map((option) => {
              const selected = selectedChoices[choice.choice_id] === option;
              return (
                <Pressable
                  disabled={adopted}
                  key={option}
                  onPress={() => onSelect(choice.choice_id, option)}
                  style={[styles.choiceOption, selected && styles.choiceOptionSelected, adopted && !selected && styles.choiceOptionMuted]}
                >
                  <Text style={[styles.choiceOptionText, selected && styles.choiceOptionTextSelected]}>{option}</Text>
                </Pressable>
              );
            })}
          </View>
        </View>
      ))}
      <View style={styles.watchCard}>
        <Text style={styles.watchTitle}>AI会和你一起观察</Text>
        {draft.unknowns_to_watch.map((item) => <Text key={item} style={styles.watchItem}>· {item}</Text>)}
        <Text style={styles.reviewRhythm}>{draft.review_rhythm.frequency}复盘一次，根据真实变化继续、调整或暂停。</Text>
      </View>
    </View>
  );
}

function StageCard({ stage, index }: { stage: GrowthPlanStage; index: number }) {
  const outcome = stage.signals.find((signal) => signal.signal_type === "OUTCOME")?.description;
  const stop = stage.signals.find((signal) => signal.signal_type === "STOP" || signal.signal_type === "PROTECTION")?.description;
  return (
    <View style={styles.stageCard}>
      <View style={styles.stageHeader}>
        <Text style={styles.stageNumber}>{String(index + 1).padStart(2, "0")}</Text>
        <View style={styles.stageHeading}><Text style={styles.stageTitle}>{stage.title}</Text><Text style={styles.stagePurpose}>{stage.purpose}</Text></View>
      </View>
      {stage.practices.map((practice) => (
        <View key={practice.practice_id} style={styles.practice}>
          <View style={styles.practiceMeta}><Text style={styles.practiceActor}>{actorLabel[practice.actor]}</Text><Text style={styles.practiceCadence}>{practice.cadence} · {practice.effort}</Text></View>
          <Text style={styles.practiceDescription}>{practice.description}</Text>
          <Text style={styles.practiceRepair}>如果不顺：{practice.repair_option}</Text>
        </View>
      ))}
      {outcome ? <Text style={styles.signalText}>看见变化：{outcome}</Text> : null}
      {stop ? <Text style={styles.stopText}>需要停下来时：{stop}</Text> : null}
      <Text style={styles.reflection}>复盘时问自己：{stage.reflection_question}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: "#F7F3EC" },
  content: { paddingHorizontal: 18, paddingBottom: 126 },
  header: { minHeight: 72, paddingHorizontal: 16, flexDirection: "row", alignItems: "center" },
  iconButton: { width: 42, height: 42, alignItems: "center", justifyContent: "center" },
  headerTitleWrap: { flex: 1, alignItems: "center" },
  headerEyebrow: { color: "#9B694A", fontSize: 10, lineHeight: 14, letterSpacing: 1.2, fontWeight: "700" },
  headerTitle: { color: "#241F1A", fontSize: 19, lineHeight: 27, fontWeight: "900" },
  centerState: { minHeight: 520, alignItems: "center", justifyContent: "center", paddingHorizontal: 28 },
  stateOrb: { width: 72, height: 72, borderRadius: 36, backgroundColor: "#E6773A", alignItems: "center", justifyContent: "center", marginBottom: 24 },
  stateOrbText: { color: "#FFFFFF", fontSize: 24, fontWeight: "900" },
  stateTitle: { color: "#2B241E", fontSize: 25, lineHeight: 34, fontWeight: "900", textAlign: "center", marginTop: 22 },
  stateCopy: { color: "#75695E", fontSize: 15, lineHeight: 24, textAlign: "center", marginTop: 10 },
  stateAction: { minHeight: 48, borderRadius: 24, paddingHorizontal: 24, alignSelf: "center", alignItems: "center", justifyContent: "center", backgroundColor: "#2F5D50", marginTop: 24 },
  stateActionText: { color: "#FFFFFF", fontSize: 15, fontWeight: "800" },
  heroCard: { borderRadius: 28, backgroundColor: "#2E574C", padding: 24, overflow: "hidden" },
  heroTopRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  heroKicker: { color: "#C8E4D8", fontSize: 11, lineHeight: 16, fontWeight: "800", letterSpacing: 0.7 },
  draftBadge: { borderRadius: 14, paddingHorizontal: 10, paddingVertical: 5, backgroundColor: "rgba(255,255,255,0.14)" },
  draftBadgeText: { color: "#F7F2E8", fontSize: 11, fontWeight: "800" },
  heroTitle: { color: "#FFFFFF", fontSize: 28, lineHeight: 38, fontWeight: "900", marginTop: 12 },
  heroCopy: { color: "#E6F2EC", fontSize: 15, lineHeight: 24, marginTop: 10 },
  durationRow: { borderTopWidth: 1, borderTopColor: "rgba(255,255,255,0.18)", marginTop: 22, paddingTop: 18, flexDirection: "row", alignItems: "baseline", flexWrap: "wrap" },
  durationValue: { color: "#F4B276", fontSize: 34, lineHeight: 40, fontWeight: "900" },
  durationUnit: { color: "#FCE7D3", fontSize: 13, fontWeight: "800", marginLeft: 7 },
  durationReason: { width: "100%", color: "#BFD8CE", fontSize: 12, lineHeight: 18, marginTop: 5 },
  reasonCard: { borderRadius: 20, backgroundColor: "#FFFDF9", padding: 19, marginTop: 14, borderWidth: 1, borderColor: "#E9DED0" },
  reasonLabel: { color: "#B45D2D", fontSize: 12, lineHeight: 18, fontWeight: "900" },
  reasonText: { color: "#4A4037", fontSize: 15, lineHeight: 25, marginTop: 7 },
  sectionTitle: { color: "#2A241F", fontSize: 21, lineHeight: 29, fontWeight: "900", marginTop: 28, marginBottom: 12 },
  stageCard: { borderRadius: 24, backgroundColor: "#FFFDF9", padding: 20, marginBottom: 14, borderWidth: 1, borderColor: "#E9DED0" },
  stageHeader: { flexDirection: "row", gap: 12 },
  stageNumber: { color: "#D66A2C", fontSize: 14, lineHeight: 21, fontWeight: "900", letterSpacing: 1 },
  stageHeading: { flex: 1 },
  stageTitle: { color: "#2A241F", fontSize: 19, lineHeight: 26, fontWeight: "900" },
  stagePurpose: { color: "#776A60", fontSize: 13, lineHeight: 20, marginTop: 3 },
  practice: { borderRadius: 16, backgroundColor: "#F5F0E8", padding: 14, marginTop: 14 },
  practiceMeta: { flexDirection: "row", justifyContent: "space-between", gap: 12 },
  practiceActor: { color: "#2F6657", fontSize: 11, fontWeight: "900" },
  practiceCadence: { color: "#8C7D70", fontSize: 11, flexShrink: 1, textAlign: "right" },
  practiceDescription: { color: "#342E29", fontSize: 15, lineHeight: 23, fontWeight: "700", marginTop: 8 },
  practiceRepair: { color: "#8A6752", fontSize: 12, lineHeight: 19, marginTop: 8 },
  signalText: { color: "#2F6657", fontSize: 12, lineHeight: 19, fontWeight: "700", marginTop: 13 },
  stopText: { color: "#A6533A", fontSize: 12, lineHeight: 19, fontWeight: "700", marginTop: 5 },
  reflection: { color: "#665B51", fontSize: 13, lineHeight: 21, fontStyle: "italic", marginTop: 12 },
  choiceCard: { borderRadius: 20, backgroundColor: "#FFFDF9", padding: 18, marginBottom: 12 },
  choiceQuestion: { color: "#332D27", fontSize: 15, lineHeight: 23, fontWeight: "800" },
  choiceOptions: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: 13 },
  choiceOption: { borderRadius: 18, paddingHorizontal: 14, paddingVertical: 9, backgroundColor: "#EFE9E0", borderWidth: 1, borderColor: "transparent" },
  choiceOptionSelected: { backgroundColor: "#E9F2EE", borderColor: "#3F7566" },
  choiceOptionMuted: { opacity: 0.38 },
  choiceOptionText: { color: "#685E55", fontSize: 13, fontWeight: "700" },
  choiceOptionTextSelected: { color: "#285E50" },
  watchCard: { borderRadius: 22, backgroundColor: "#E9F0EC", padding: 20, marginTop: 14 },
  watchTitle: { color: "#29584B", fontSize: 16, lineHeight: 23, fontWeight: "900" },
  watchItem: { color: "#46675E", fontSize: 13, lineHeight: 21, marginTop: 7 },
  reviewRhythm: { color: "#29584B", fontSize: 12, lineHeight: 19, fontWeight: "800", marginTop: 12 },
  questionCard: { borderRadius: 18, backgroundColor: "#FFFDF9", padding: 17, marginBottom: 10, flexDirection: "row", gap: 13 },
  questionIndex: { color: "#D66A2C", fontSize: 12, fontWeight: "900" },
  questionText: { flex: 1, color: "#3D352E", fontSize: 15, lineHeight: 23, fontWeight: "700" },
  limitationText: { color: "#776A60", fontSize: 12, lineHeight: 19, marginTop: 8 },
  message: { color: "#8B4B2A", fontSize: 13, lineHeight: 20, textAlign: "center", marginTop: 18 },
  footer: { position: "absolute", left: 0, right: 0, bottom: 0, backgroundColor: "rgba(247,243,236,0.97)", borderTopWidth: 1, borderTopColor: "#E5DACE", paddingHorizontal: 16, paddingTop: 11, paddingBottom: 14, flexDirection: "row", gap: 10 },
  secondaryButton: { minHeight: 50, borderRadius: 25, paddingHorizontal: 17, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "#B6A79A" },
  secondaryButtonText: { color: "#5E5147", fontSize: 13, fontWeight: "800" },
  primaryButton: { flex: 1, minHeight: 50, borderRadius: 25, alignItems: "center", justifyContent: "center", backgroundColor: "#D66A2C" },
  primaryButtonText: { color: "#FFFFFF", fontSize: 15, fontWeight: "900" },
  disabledButton: { opacity: 0.42 },
});
