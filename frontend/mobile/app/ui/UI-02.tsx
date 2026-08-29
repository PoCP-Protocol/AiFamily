import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import type { GrowthFocusId } from "@/lib/family/core-growth";
import { UI02_ASSESSMENT_ANSWER_OPTIONS, getUi02DeepAssessmentQuestions, type Ui02AssessmentAnswer } from "@/lib/family/ui02-assessment-design";
import { UI02_ORIGINAL_FOCUS_LAYOUT } from "@/lib/family/ui02-assessment-layout";
import { createMobileRequestId, familyApi } from "@/lib/family/family-api-client";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";
import { haptic } from "@/lib/haptics";

type FamilyStructure = "双亲家庭" | "单亲家庭" | "重组家庭";
type ChildGender = "男孩" | "女孩";
type ServicePreference = "看文字建议" | "生成计划草案" | "只保留记录";

type RemoteAssessmentSession = {
  assessment_session_id: string;
  subject_person_id: string;
  tool_ref: string;
  tool_version: number;
  row_version: number;
  status: "IN_PROGRESS" | "SUBMITTED" | "EXITED";
  responses: { item_ref: string; response_value: string | boolean; revision: number }[];
};

type RemoteAssessmentProjection = {
  projection_version: "UI02_FAMILY_ASSESSMENT_V1";
  availability: "AVAILABLE" | "CONSENT_REQUIRED" | "NO_SUBJECT" | "POLICY_BLOCKED";
  subjects: { person_id: string; display_name: string; availability: "AVAILABLE" | "CONSENT_REQUIRED" }[];
  tool: { tool_ref: string; version_no: number; title: string; purpose: string; evidence_level: "E1"; boundary: { not_a_score: true; not_a_diagnosis: true; training_use: false } } | null;
  sessions: RemoteAssessmentSession[];
};

type AssessmentReceipt = { session: RemoteAssessmentSession; replayed: boolean; evidence_id?: string };

const FOCUS_ICON: Record<string, { name: "book.fill" | "heart.fill" | "message.fill" | "phone.fill" | "shield.fill"; color: string }> = {
  LEARNING_HABITS: { name: "book.fill", color: "#2F9BE0" },
  EMOTION_REGULATION: { name: "message.fill", color: "#F5943A" },
  PARENT_CHILD_COMMUNICATION: { name: "heart.fill", color: "#F0555C" },
  DEVICE_USE_CONTEXT: { name: "phone.fill", color: "#5B7CF0" },
  SELF_REGULATION: { name: "shield.fill", color: "#3FB667" },
};

const CHILD_STAGE_OPTIONS: readonly string[] = [
  "3岁（学龄前）",
  "4-5岁（幼儿园）",
  "6岁（小学一年级）",
  "7岁（小学二年级）",
  "8岁（小学三年级）",
  "9岁（小学四年级）",
  "10岁（小学四年级）",
  "11岁（小学五年级）",
  "12岁（小学六年级）",
  "13岁（初中一年级）",
  "14岁（初中二年级）",
  "15岁（初中三年级）",
  "16岁及以上（高中及以上）",
];
const DEFAULT_CHILD_STAGE = "10岁（小学四年级）";
const DEFAULT_GROWTH_FOCUS = "PARENT_CHILD_COMMUNICATION";
const ASSESSMENT_BOUNDARY_TEXT = "我知道这只是家庭自查，不给孩子打分，不做诊断或排名。";
const SERVICE_PREFERENCE_OPTIONS: readonly ServicePreference[] = ["看文字建议", "生成计划草案", "只保留记录"];

export default function FamilyAssessmentScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const { selectedGrowthFocus, assessmentSyncState, selectGrowthFocus, setAssessmentSyncState } = useFamilyMobile();
  const [familyStructure, setFamilyStructure] = useState<FamilyStructure>("双亲家庭");
  const [childGender, setChildGender] = useState<ChildGender>("男孩");
  const [servicePreference, setServicePreference] = useState<ServicePreference>("看文字建议");
  const [boundaryAccepted, setBoundaryAccepted] = useState(false);
  const [deepAnswers, setDeepAnswers] = useState<Record<string, Ui02AssessmentAnswer>>({});
  const [childStage, setChildStage] = useState(DEFAULT_CHILD_STAGE);
  const [childStageOpen, setChildStageOpen] = useState(false);
  const [projection, setProjection] = useState<RemoteAssessmentProjection | null>(null);
  const [projectionState, setProjectionState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [subjectId, setSubjectId] = useState<string | null>(null);
  const [submissionError, setSubmissionError] = useState<string | null>(null);
  const retryKeys = useRef<Record<string, string>>({});
  const selectedFocusId = (selectedGrowthFocus ?? DEFAULT_GROWTH_FOCUS) as GrowthFocusId;
  const selectedQuestions = getUi02DeepAssessmentQuestions(selectedFocusId);
  const answeredQuestionCount = selectedQuestions.filter((question) => deepAnswers[question.itemRef]).length;
  const canSubmitAssessment = boundaryAccepted && !!selectedGrowthFocus && answeredQuestionCount === selectedQuestions.length;

  const keyFor = (fingerprint: string) => {
    retryKeys.current[fingerprint] ??= createMobileRequestId(fingerprint.replace(/[^a-z0-9]+/gi, "-").toLowerCase());
    return retryKeys.current[fingerprint];
  };

  const loadAssessment = useCallback(async () => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) {
      setProjection(null);
      setProjectionState("idle");
      return;
    }
    setProjectionState("loading");
    try {
      const next = await familyApi.getFamilyAssessment<RemoteAssessmentProjection>(session.token, session.selectedFamily.family_id);
      setProjection(next);
      setProjectionState("ready");
    } catch {
      setProjectionState("error");
    }
  }, [session.selectedFamily, session.status, session.token]);

  useEffect(() => { void loadAssessment(); }, [loadAssessment]);

  useEffect(() => {
    if (!selectedGrowthFocus) selectGrowthFocus(DEFAULT_GROWTH_FOCUS);
  }, [selectGrowthFocus, selectedGrowthFocus]);

  useEffect(() => {
    const available = projection?.subjects.filter((subject) => subject.availability === "AVAILABLE") ?? [];
    setSubjectId((current) => {
      if (current && available.some((subject) => subject.person_id === current)) return current;
      return available[0]?.person_id ?? null;
    });
  }, [projection]);

  useEffect(() => {
    if (!projection || !subjectId) return;
    const active = projection.sessions.find((item) => item.subject_person_id === subjectId && item.status === "IN_PROGRESS");
    const focus = active?.responses.find((item) => item.item_ref === "FOCUS")?.response_value;
    if (typeof focus === "string" && UI02_ORIGINAL_FOCUS_LAYOUT.some((item) => item.id === focus)) selectGrowthFocus(focus as typeof selectedGrowthFocus & string);
    if (active) {
      const answerIds = new Set(UI02_ASSESSMENT_ANSWER_OPTIONS.map((option) => option.id));
      setDeepAnswers((current) => {
        const next = { ...current };
        for (const response of active.responses) {
          if (typeof response.response_value === "string" && answerIds.has(response.response_value as Ui02AssessmentAnswer)) {
            next[response.item_ref] = response.response_value as Ui02AssessmentAnswer;
          }
        }
        return next;
      });
    }
  }, [projection, selectGrowthFocus, selectedGrowthFocus, subjectId]);

  const saveFocus = async () => {
    if (!selectedGrowthFocus || !canSubmitAssessment) return;
    haptic.light();
    if (session.status === "connected" && session.token && session.selectedFamily) {
      if (!projection || projection.availability !== "AVAILABLE" || !projection.tool || !subjectId) {
        setSubmissionError("请先选择已获得测评同意的孩子。");
        return;
      }
      try {
        setAssessmentSyncState("syncing");
        setSubmissionError(null);
        const familyId = session.selectedFamily.family_id;
        const active = projection.sessions.find((item) => item.subject_person_id === subjectId && item.status === "IN_PROGRESS");
        const started = active ? { session: active } : await familyApi.startFamilyAssessment<AssessmentReceipt>(session.token, familyId, { subject_person_id: subjectId, tool_ref: projection.tool.tool_ref }, keyFor(`ui02-start:${familyId}:${subjectId}:${projection.tool.tool_ref}`));
        const sessionId = started.session.assessment_session_id;
        const focusReceipt = await familyApi.saveFamilyAssessmentResponse<AssessmentReceipt>(session.token, familyId, sessionId, { item_ref: "FOCUS", response_type: "SINGLE_CHOICE", response_value: selectedGrowthFocus }, keyFor(`ui02-focus:${sessionId}:${selectedGrowthFocus}`));
        const familyStructureValue = familyStructure === "双亲家庭" ? "TWO_PARENT" : familyStructure === "单亲家庭" ? "SINGLE_PARENT" : "BLENDED";
        await familyApi.saveFamilyAssessmentResponse<AssessmentReceipt>(session.token, familyId, sessionId, { item_ref: "FAMILY_STRUCTURE", response_type: "SINGLE_CHOICE", response_value: familyStructureValue }, keyFor(`ui02-structure:${sessionId}:${familyStructureValue}`));
        const genderValue = childGender === "男孩" ? "BOY" : "GIRL";
        await familyApi.saveFamilyAssessmentResponse<AssessmentReceipt>(session.token, familyId, sessionId, { item_ref: "CHILD_GENDER", response_type: "SINGLE_CHOICE", response_value: genderValue }, keyFor(`ui02-gender:${sessionId}:${genderValue}`));
        for (const question of selectedQuestions) {
          const answer = deepAnswers[question.itemRef];
          if (answer) {
            await familyApi.saveFamilyAssessmentResponse<AssessmentReceipt>(session.token, familyId, sessionId, { item_ref: question.itemRef, response_type: "SINGLE_CHOICE", response_value: answer }, keyFor(`ui02-deep:${sessionId}:${question.itemRef}:${answer}`));
          }
        }
        const submitted = await familyApi.submitFamilyAssessment<AssessmentReceipt>(session.token, familyId, sessionId, keyFor(`ui02-submit:${sessionId}:${focusReceipt.session.row_version ?? 0}`));
        setProjection((current) => current ? { ...current, sessions: [submitted.session, ...current.sessions.filter((item) => item.assessment_session_id !== sessionId)] } : current);
        setAssessmentSyncState("synced");
      } catch {
        setAssessmentSyncState("error");
        setSubmissionError("测评暂时没有提交成功；已使用相同请求标识，可安全重试，不会重复创建记录。");
        return;
      }
    } else {
      setAssessmentSyncState("local");
    }
    haptic.success();
    router.push("/ui/UI-02-result" as Href);
  };

  return (
    <ScreenContainer edges={["top", "left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView refreshControl={<FamilyRefreshControl />} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.topBar}>
          <Pressable accessibilityLabel="返回" onPress={() => router.back()} hitSlop={10} style={styles.iconButton}>
            <Text style={[styles.backArrow, { color: colors.text }]}>‹</Text>
          </Pressable>
          <Text style={[styles.screenTitle, { color: colors.text }]}>家庭测评</Text>
          <View style={styles.topActions}>
            <IconSymbol name="ellipsis" size={22} color={colors.text} />
            <View style={[styles.contextCircle, { borderColor: colors.text }]} />
          </View>
        </View>

        <View style={styles.stepBlock}>
          <Text style={[styles.stepText, { color: colors.text }]}>第 2 / 5 步</Text>
          <View style={[styles.progressTrack, { backgroundColor: colors.border }]}>
            <View style={[styles.progressValue, { backgroundColor: "#1B7CF2" }]} />
          </View>
        </View>

        <View style={styles.questionBlock}>
          <Text style={[styles.questionTitle, { color: colors.text }]}>最近最想先支持孩子的哪一方面？</Text>
          <Text style={[styles.questionHint, { color: colors.muted }]}>请选择最贴近最近情况的一项。</Text>
        </View>

        <View style={styles.focusList}>
          {UI02_ORIGINAL_FOCUS_LAYOUT.map((item) => {
            const selected = item.id === selectedGrowthFocus;
            const icon = FOCUS_ICON[item.id] ?? FOCUS_ICON.PARENT_CHILD_COMMUNICATION;
            return (
              <Pressable
                key={item.id}
                accessibilityRole="radio"
                accessibilityState={{ selected }}
                onPress={() => { selectGrowthFocus(item.id); haptic.selection(); }}
                style={({ pressed }) => [
                  styles.focusCard,
                  { backgroundColor: selected ? "#EDF4FF" : colors.background, borderColor: selected ? "#1B7CF2" : colors.border },
                  selected && styles.focusCardSelected,
                  pressed && styles.pressed,
                ]}
              >
                <View style={[styles.focusIcon, { backgroundColor: icon.color }]}>
                  <IconSymbol name={icon.name} size={21} color="#FFFFFF" />
                </View>
                <View style={styles.focusCopy}>
                  <Text style={[styles.focusTitle, { color: colors.text }]}>{item.title}</Text>
                  <Text style={[styles.focusSubtitle, { color: colors.muted }]}>{item.subtitle}</Text>
                </View>
                {selected ? <IconSymbol name="checkmark.circle.fill" size={22} color="#1B7CF2" /> : <View style={styles.checkSpacer} />}
              </Pressable>
            );
          })}
        </View>

        <View style={styles.deepBlock}>
          <View style={styles.deepHeader}>
            <Text style={[styles.extraTitle, { color: colors.text }]}>再了解一点</Text>
            <Text style={[styles.questionHint, { color: colors.muted }]}>{answeredQuestionCount} / {selectedQuestions.length}</Text>
          </View>
          {selectedQuestions.map((question) => (
            <View key={question.itemRef} style={[styles.deepQuestionCard, { backgroundColor: colors.background, borderColor: colors.border }]}> 
              <Text style={[styles.deepQuestionText, { color: colors.text }]}>{question.text}</Text>
              <View style={styles.answerGrid}>
                {UI02_ASSESSMENT_ANSWER_OPTIONS.map((option) => {
                  const selected = deepAnswers[question.itemRef] === option.id;
                  return (
                    <Pressable
                      key={option.id}
                      accessibilityRole="radio"
                      accessibilityState={{ selected }}
                      onPress={() => { setDeepAnswers((current) => ({ ...current, [question.itemRef]: option.id })); haptic.selection(); }}
                      style={({ pressed }) => [
                        styles.answerChip,
                        { borderColor: selected ? "#1B7CF2" : colors.border, backgroundColor: selected ? "#EDF4FF" : "#FFFFFF" },
                        pressed && styles.pressed,
                      ]}
                    >
                      <Text style={[styles.answerChipText, { color: selected ? "#1B7CF2" : colors.muted }]}>{option.label}</Text>
                    </Pressable>
                  );
                })}
              </View>
            </View>
          ))}
        </View>

        <View style={styles.extraBlock}>
          <Text style={[styles.extraTitle, { color: colors.text }]}>补充信息<Text style={[styles.optional, { color: colors.muted }]}>（可选）</Text></Text>
          <View style={styles.infoRow}>
            <Text style={[styles.infoLabel, { color: colors.text }]}>孩子年龄/阶段</Text>
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ expanded: childStageOpen }}
              onPress={() => { setChildStageOpen((value) => !value); haptic.selection(); }}
              style={({ pressed }) => [styles.ageSelector, { borderColor: childStageOpen ? "#1B7CF2" : colors.border, backgroundColor: colors.background }, pressed && styles.pressed]}
            >
              <Text style={[styles.ageText, { color: colors.text }]}>{childStage}</Text>
              <Text style={[styles.chevron, { color: colors.muted }, childStageOpen && styles.chevronOpen]}>⌄</Text>
            </Pressable>
          </View>
          {childStageOpen ? (
            <View style={[styles.stageMenu, { borderColor: colors.border, backgroundColor: colors.background }]}>
              {CHILD_STAGE_OPTIONS.map((option) => {
                const selected = option === childStage;
                return (
                  <Pressable
                    key={option}
                    accessibilityRole="radio"
                    accessibilityState={{ selected }}
                    onPress={() => { setChildStage(option); setChildStageOpen(false); haptic.selection(); }}
                    style={({ pressed }) => [styles.stageOption, selected && { backgroundColor: "#EDF4FF" }, pressed && styles.pressed]}
                  >
                    <Text style={[styles.stageOptionText, { color: selected ? "#1B7CF2" : colors.text }]}>{option}</Text>
                    {selected ? <IconSymbol name="checkmark.circle.fill" size={18} color="#1B7CF2" /> : null}
                  </Pressable>
                );
              })}
            </View>
          ) : null}
          <ChoiceRow label="家庭情况" options={["双亲家庭", "单亲家庭", "重组家庭"]} value={familyStructure} onChange={setFamilyStructure} colors={colors} />
          <ChoiceRow label="孩子性别" options={["男孩", "女孩"]} value={childGender} onChange={setChildGender} colors={colors} />
          <ChoiceRow label="服务偏好" options={SERVICE_PREFERENCE_OPTIONS} value={servicePreference} onChange={setServicePreference} colors={colors} />
        </View>

        <Pressable
          accessibilityRole="checkbox"
          accessibilityState={{ checked: boundaryAccepted }}
          onPress={() => { setBoundaryAccepted((value) => !value); haptic.selection(); }}
          style={({ pressed }) => [styles.consentRow, { borderColor: boundaryAccepted ? "#1B7CF2" : colors.border, backgroundColor: colors.background }, pressed && styles.pressed]}
        >
          <IconSymbol name={boundaryAccepted ? "checkmark.circle.fill" : "shield.fill"} size={20} color={boundaryAccepted ? "#1B7CF2" : colors.muted} />
          <Text style={[styles.consentText, { color: colors.muted }]}>{ASSESSMENT_BOUNDARY_TEXT}</Text>
        </Pressable>

        {projectionState === "error" ? <Pressable onPress={() => void loadAssessment()} style={styles.inlineNotice}><Text style={[styles.saveHint, { color: colors.muted }]}>暂时无法读取测评记录，点击重试</Text></Pressable> : null}
        {projection && projection.availability !== "AVAILABLE" ? <Text style={[styles.saveHint, { color: colors.muted }]}>{projection.availability === "POLICY_BLOCKED" ? "当前家庭策略尚未开放测评。" : projection.availability === "CONSENT_REQUIRED" ? "请先完成孩子的测评同意。" : "当前家庭还没有可测评的孩子。"}</Text> : null}

        {assessmentSyncState === "error" ? (
          <Text style={[styles.saveHint, { color: colors.muted }]}>{submissionError ?? "暂时无法同步，请稍后重试。"}</Text>
        ) : null}
        {submissionError && assessmentSyncState !== "error" ? <Text style={[styles.saveHint, { color: colors.muted }]}>{submissionError}</Text> : null}
        <Pressable
          accessibilityRole="button"
          accessibilityHint={`${ASSESSMENT_BOUNDARY_TEXT}${boundaryAccepted ? " 已确认。" : " 请先确认。"}${answeredQuestionCount === selectedQuestions.length ? " 已完成补充问题。" : " 请完成补充问题。"}`}
          disabled={!canSubmitAssessment || assessmentSyncState === "syncing" || (session.status === "connected" && (!subjectId || projection?.availability !== "AVAILABLE"))}
          onPress={() => { void saveFocus(); }}
          style={({ pressed }) => [
            styles.primaryButton,
            { backgroundColor: canSubmitAssessment ? "#1B7CF2" : colors.border },
            pressed && canSubmitAssessment && styles.pressed,
          ]}
        >
          <Text style={styles.primaryButtonText}>{assessmentSyncState === "syncing" ? "正在保存" : "下一步"}</Text>
        </Pressable>
      </ScrollView>
    </ScreenContainer>
  );
}

function ChoiceRow<T extends string>({
  label,
  options,
  value,
  onChange,
  colors,
}: {
  label: string;
  options: readonly T[];
  value: T;
  onChange: (next: T) => void;
  colors: ReturnType<typeof useColors>;
}) {
  return (
    <View style={styles.infoRow}>
      <Text style={[styles.infoLabel, { color: colors.text }]}>{label}</Text>
      <View style={styles.chips}>
        {options.map((option) => {
          const selected = option === value;
          return (
            <Pressable
              key={option}
              onPress={() => { onChange(option); haptic.selection(); }}
              style={({ pressed }) => [
                styles.chip,
                { backgroundColor: colors.background, borderColor: selected ? "#1B7CF2" : colors.border },
                pressed && styles.pressed,
              ]}
            >
              <Text style={[styles.chipText, { color: selected ? "#1B7CF2" : colors.muted }]}>{option}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { flexGrow: 1, paddingHorizontal: 14, paddingTop: 6, paddingBottom: 20, gap: 0 },
  topBar: { height: 48, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  iconButton: { width: 36, height: 40, justifyContent: "center", alignItems: "flex-start" },
  backArrow: { fontSize: 35, lineHeight: 38, fontWeight: "300", marginTop: -4 },
  screenTitle: { position: "absolute", left: 48, right: 48, textAlign: "center", fontSize: 17, lineHeight: 23, fontWeight: "800" },
  topActions: { flexDirection: "row", alignItems: "center", gap: 14, minWidth: 50, justifyContent: "flex-end" },
  contextCircle: { width: 16, height: 16, borderWidth: 1.6, borderRadius: 8 },
  stepBlock: { marginTop: 18, gap: 10 },
  stepText: { fontSize: 15, lineHeight: 21, fontWeight: "800" },
  progressTrack: { height: 6, borderRadius: 3, overflow: "hidden" },
  progressValue: { width: "50%", height: "100%", borderRadius: 3 },
  questionBlock: { marginTop: 20, gap: 3 },
  questionTitle: { fontSize: 20, lineHeight: 28, fontWeight: "800" },
  questionHint: { fontSize: 14, lineHeight: 20 },
  focusList: { marginTop: 14, gap: 8 },
  focusCard: { minHeight: 63, borderWidth: 1, borderRadius: 14, paddingHorizontal: 14, flexDirection: "row", alignItems: "center", gap: 12 },
  focusCardSelected: { borderWidth: 1.8, paddingHorizontal: 13.2 },
  focusIcon: { width: 40, height: 40, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  focusCopy: { flex: 1, gap: 1 },
  focusTitle: { fontSize: 15, lineHeight: 20, fontWeight: "800" },
  focusSubtitle: { fontSize: 12, lineHeight: 17 },
  checkSpacer: { width: 22, height: 22 },
  deepBlock: { marginTop: 18, gap: 10 },
  deepHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  deepQuestionCard: { borderWidth: 1, borderRadius: 14, padding: 12, gap: 8 },
  deepQuestionText: { fontSize: 14, lineHeight: 20, fontWeight: "800" },
  answerGrid: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  answerChip: { minHeight: 30, borderWidth: 1, borderRadius: 999, paddingHorizontal: 10, justifyContent: "center", alignItems: "center" },
  answerChipText: { fontSize: 12, lineHeight: 16, fontWeight: "800" },
  extraBlock: { marginTop: 18, gap: 10 },
  extraTitle: { fontSize: 16, lineHeight: 22, fontWeight: "800" },
  optional: { fontSize: 13, fontWeight: "500" },
  infoRow: { minHeight: 34, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 10 },
  infoLabel: { fontSize: 14, lineHeight: 20 },
  ageSelector: { minHeight: 32, borderWidth: 1, borderRadius: 8, paddingHorizontal: 9, flexDirection: "row", alignItems: "center", gap: 5 },
  chevronOpen: { transform: [{ rotate: "180deg" }] },
  stageMenu: { marginTop: 6, borderWidth: 1, borderRadius: 10, overflow: "hidden" },
  stageOption: { minHeight: 40, paddingHorizontal: 12, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  stageOptionText: { fontSize: 13, lineHeight: 18, fontWeight: "700" },
  ageText: { fontSize: 12, lineHeight: 17, fontWeight: "700" },
  chevron: { fontSize: 14, lineHeight: 16 },
  chips: { flexDirection: "row", alignItems: "center", gap: 5 },
  chip: { minHeight: 29, borderWidth: 1, borderRadius: 6, paddingHorizontal: 8, justifyContent: "center", alignItems: "center" },
  chipText: { fontSize: 12, lineHeight: 16, fontWeight: "700" },
  inlineNotice: { marginTop: 8 },
  consentRow: { marginTop: 16, minHeight: 46, borderWidth: 1, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 9, flexDirection: "row", alignItems: "center", gap: 8 },
  consentText: { flex: 1, fontSize: 12, lineHeight: 18 },
  saveHint: { marginTop: 12, fontSize: 12, lineHeight: 18, textAlign: "center" },
  primaryButton: { marginTop: "auto", minHeight: 50, borderRadius: 25, alignItems: "center", justifyContent: "center" },
  primaryButtonText: { color: "#FFFFFF", fontSize: 17, lineHeight: 23, fontWeight: "800" },
  pressed: { opacity: 0.78, transform: [{ scale: 0.98 }] },
  disabled: { opacity: 0.48 },
});
