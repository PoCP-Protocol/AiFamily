import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { useColors } from "@/hooks/use-colors";
import {
  createMobileRequestId,
  FamilyApiError,
  familyApi,
} from "@/lib/family/family-api-client";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";

type AssessmentResult = {
  result_id: string;
  assessment_session_id: string;
  subject: { person_id: string; display_name: string };
  focus_ref: string;
  family_need_ref: string;
  title: string;
  explanation: {
    headline: string;
    summary: string;
    observations: {
      item_ref: string;
      response_value: string | boolean;
      kind: string;
    }[];
    hypothesis: string;
    recommendations: { text: string; source: string; status: "DRAFT" }[];
  };
  evidence_lineage: {
    source_refs: string[];
    tool_ref: string;
    tool_version: number;
    submitted_at: string | null;
  };
  ai: {
    generator: string;
    model: string | null;
    model_version: string | null;
    prompt_version: string | null;
    context_snapshot_ref: string | null;
    provenance_refs: string[];
    model_gateway_status: "NOT_INVOKED" | "DRAFT" | "BLOCKED";
    may_mutate_business_state: false;
  };
  boundary: "FAMILY_PERSPECTIVE_NOT_SCORE_OR_DIAGNOSIS";
  draft_metadata: { boundary_labels: string[]; review_required: boolean };
};

type AssessmentResultProjection = {
  projection_version: "ASSESSMENT_RESULT_V1";
  tenant_id: string;
  family_id: string;
  status: "READY" | "NO_RESULT" | "CONSENT_REQUIRED" | "POLICY_BLOCKED";
  result: AssessmentResult | null;
};

type SupportLoopProjection = {
  projection_version: "ASSESSMENT_SUPPORT_LOOP_V1";
  tenant_id: string;
  family_id: string;
  status: "READY" | "NO_RESULT" | "CONSENT_REQUIRED" | "POLICY_BLOCKED";
  assessment_session_id: string | null;
  small_step: {
    action_ref: "TRY_TONIGHT";
    action_text: string;
    status: "STARTED";
    available_for_checkin: "NEXT_DAY";
    available_for_checkin_at: string;
    boundary: "FAMILY_CHOSEN_ACTION_NOT_OUTCOME";
  } | null;
  latest_feedback: {
    feedback_type: "LIKE" | "NOT_LIKE" | "ADD_CONTEXT";
    supplement_text: string | null;
    boundary: "FEEDBACK_REFINES_PERSPECTIVE_NOT_FACT";
  } | null;
  latest_checkin: {
    outcome: "HELPED" | "NO_CHANGE" | "NOT_TRIED";
    note: string | null;
    boundary: "FAMILY_FEEDBACK_NOT_OUTCOME_PROOF";
  } | null;
};

export default function GrowthExplanationScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const { assessmentNeedText, restartAssessment } = useFamilyMobile();
  const [remote, setRemote] = useState<AssessmentResultProjection | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "ready" | "error">(
    "idle",
  );
  const [retryNonce, setRetryNonce] = useState(0);
  const [supportRemote, setSupportRemote] =
    useState<SupportLoopProjection | null>(null);
  const [supportState, setSupportState] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [supportRetryNonce, setSupportRetryNonce] = useState(0);
  const [showDetails, setShowDetails] = useState(false);
  const [perspectiveFeedback, setPerspectiveFeedback] = useState<
    "LIKE" | "NOT_LIKE" | "ADD_CONTEXT" | null
  >(null);
  const [supplementText, setSupplementText] = useState("");
  const [feedbackState, setFeedbackState] = useState<
    "idle" | "saving" | "saved" | "retry"
  >("idle");
  const [smallStepState, setSmallStepState] = useState<
    "idle" | "saving" | "saved" | "retry"
  >("idle");
  const [checkinOutcome, setCheckinOutcome] = useState<
    "HELPED" | "NO_CHANGE" | "NOT_TRIED" | null
  >(null);
  const [checkinNote, setCheckinNote] = useState("");
  const [checkinState, setCheckinState] = useState<
    "idle" | "saving" | "saved" | "retry" | "too_soon"
  >("idle");
  const operationKeys = useRef<Record<string, string>>({});

  const connected =
    session.status === "connected" &&
    !!session.token &&
    !!session.selectedFamily;
  const result = remote?.result;
  const assessmentSessionId =
    supportRemote?.assessment_session_id ?? result?.assessment_session_id ?? null;

  const keyFor = (fingerprint: string) => {
    operationKeys.current[fingerprint] ??= createMobileRequestId(
      fingerprint.replace(/[^a-z0-9]+/gi, "-").toLowerCase(),
    );
    return operationKeys.current[fingerprint];
  };

  const submitPerspectiveFeedback = async (
    feedback: "LIKE" | "NOT_LIKE" | "ADD_CONTEXT",
  ) => {
    setPerspectiveFeedback(feedback);
    if (!connected) {
      setFeedbackState("saving");
      setFeedbackState("saved");
      return;
    }
    if (!assessmentSessionId) {
      setFeedbackState("retry");
      return;
    }
    setFeedbackState("saving");
    try {
      await familyApi.submitAssessmentSupportCardFeedback(
        session.token!,
        session.selectedFamily!.family_id,
        {
          assessment_session_id: assessmentSessionId,
          feedback_type: feedback,
          ...(feedback === "ADD_CONTEXT" && supplementText.trim()
            ? { supplement_text: supplementText.trim() }
            : {}),
        },
        keyFor(
          `support-feedback:${assessmentSessionId}:${feedback}:${supplementText.trim()}`,
        ),
      );
      setFeedbackState("saved");
      setSupportRetryNonce((value) => value + 1);
    } catch {
      setFeedbackState("retry");
    }
  };

  const submitSupplement = () => {
    if (!supplementText.trim()) {
      setFeedbackState("retry");
      return;
    }
    submitPerspectiveFeedback("ADD_CONTEXT");
  };

  const startSmallStep = () => {
    if (!connected) {
      setSmallStepState("saving");
      setSmallStepState("saved");
      return;
    }
    if (!assessmentSessionId) {
      setSmallStepState("retry");
      return;
    }
    setSmallStepState("saving");
    void familyApi
      .startAssessmentSupportCardSmallStep(
        session.token!,
        session.selectedFamily!.family_id,
        { assessment_session_id: assessmentSessionId, action_ref: "TRY_TONIGHT" },
        keyFor(`support-small-step:${assessmentSessionId}:TRY_TONIGHT`),
      )
      .then(() => {
        setSmallStepState("saved");
        setSupportRetryNonce((value) => value + 1);
      })
      .catch(() => setSmallStepState("retry"));
  };

  const saveForLater = () => {
    if (connected) {
      setSmallStepState("retry");
      return;
    }
    setSmallStepState("saved");
  };

  const submitCheckin = (outcome: "HELPED" | "NO_CHANGE" | "NOT_TRIED") => {
    setCheckinOutcome(outcome);
    if (!connected || !assessmentSessionId) {
      setCheckinState("retry");
      return;
    }
    setCheckinState("saving");
    void familyApi
      .recordAssessmentSupportCardCheckin(
        session.token!,
        session.selectedFamily!.family_id,
        {
          assessment_session_id: assessmentSessionId,
          outcome,
          ...(checkinNote.trim() ? { note: checkinNote.trim() } : {}),
        },
        keyFor(
          `support-checkin:${assessmentSessionId}:${outcome}:${checkinNote.trim()}`,
        ),
      )
      .then(() => {
        setCheckinState("saved");
        setSupportRetryNonce((value) => value + 1);
      })
      .catch((error: unknown) => {
        setCheckinState(
          error instanceof FamilyApiError &&
            error.code === "assessment_checkin_not_yet_available"
            ? "too_soon"
            : "retry",
        );
      });
  };

  useEffect(() => {
    if (
      session.status !== "connected" ||
      !session.token ||
      !session.selectedFamily
    ) {
      setState("idle");
      return;
    }
    let active = true;
    setState("loading");
    void familyApi
      .getLatestAssessmentResult<AssessmentResultProjection>(
        session.token,
        session.selectedFamily.family_id,
      )
      .then((result) => {
        if (active) {
          setRemote(result);
          setState("ready");
        }
      })
      .catch(() => {
        if (active) setState("error");
      });
    return () => {
      active = false;
    };
  }, [retryNonce, session.selectedFamily, session.status, session.token]);

  useEffect(() => {
    if (
      session.status !== "connected" ||
      !session.token ||
      !session.selectedFamily ||
      !result
    ) {
      setSupportRemote(null);
      setSupportState("idle");
      return;
    }
    let active = true;
    setSupportState("loading");
    void familyApi
      .getLatestAssessmentSupportCard<SupportLoopProjection>(
        session.token,
        session.selectedFamily.family_id,
      )
      .then((support) => {
        if (!active) return;
        setSupportRemote(support);
        setSupportState("ready");
        setFeedbackState(support.latest_feedback ? "saved" : "idle");
        setSmallStepState(support.small_step ? "saved" : "idle");
        if (support.latest_checkin) {
          setCheckinOutcome(support.latest_checkin.outcome);
          setCheckinNote(support.latest_checkin.note ?? "");
          setCheckinState("saved");
        }
      })
      .catch(() => {
        if (active) setSupportState("error");
      });
    return () => {
      active = false;
    };
  }, [
    result,
    session.selectedFamily,
    session.status,
    session.token,
    supportRetryNonce,
  ]);

  if (state === "loading")
    return (
      <ScreenContainer edges={["left", "right", "bottom"]}>
        <Stack.Screen
          options={{
            headerShown: true,
            title: "家庭支持整理",
            headerBackTitle: "退出",
          }}
        />
        <View style={styles.emptyPage}>
          <ActivityIndicator color={colors.tint} />
          <Text style={[styles.emptyTitle, { color: colors.text }]}>
            正在把这件小事整理清楚
          </Text>
          <Text style={[styles.emptyText, { color: colors.muted }]}>
            只根据本次已提交的少量回答整理支持参考。
          </Text>
        </View>
      </ScreenContainer>
    );

  const unavailableText =
    remote?.status === "CONSENT_REQUIRED"
        ? "测评授权已撤回，这次结果已停止展示。"
      : remote?.status === "POLICY_BLOCKED"
        ? "这项家庭整理暂时还不能查看。"
        : "还没有已提交的家庭测评。";
  const firstRecommendation =
    result?.explanation.recommendations[0]?.text ??
    "今天先留出十分钟，和孩子一起说清楚这件小事。";

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen
        options={{
          headerShown: true,
          title: "家庭支持整理",
          headerBackTitle: "退出",
        }}
      />
      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        {state === "error" ? (
          <View style={styles.notice}>
            <Text style={styles.noticeTitle}>暂时无法读取这次整理</Text>
            <Text style={styles.noticeText}>
              请稍后重试；已有提交不会因为读取失败而重复创建。
            </Text>
            <Pressable
              onPress={() => setRetryNonce((value) => value + 1)}
              style={styles.retryButton}
            >
              <Text style={styles.retryText}>重新读取</Text>
            </Pressable>
          </View>
        ) : null}
        {!result ? (
          <View style={styles.emptyPage}>
            <Text style={styles.emptyKicker}>家庭理解</Text>
            <Text style={[styles.emptyTitle, { color: colors.text }]}>
              {unavailableText}
            </Text>
            <Text style={[styles.emptyText, { color: colors.muted }]}>
              先从一件正在发生的家庭小事开始，完成后你会得到一张支持卡，帮助你和孩子把这件小事说清楚。
            </Text>
            <Pressable
              testID="assessment-empty-start"
              accessibilityRole="button"
              onPress={() => router.replace("/ui/UI-02" as Href)}
              style={({ pressed }) => [
                styles.primaryButton,
                { backgroundColor: colors.tint },
                pressed && styles.pressed,
              ]}
            >
              <Text style={styles.primaryButtonText}>先整理一件家庭小事</Text>
            </Pressable>
          </View>
        ) : (
          <>
            <View style={styles.hero}>
              <View style={styles.heroIcon}>
                <Text style={styles.heroIconText}>✓</Text>
              </View>
              <View style={styles.heroCopy}>
                <Text style={styles.badge}>家庭支持卡 · 家庭范围 · 可回读结果</Text>
                <Text style={styles.heroTitle}>
                  今晚，先让这件事轻一点
                </Text>
                <Text style={styles.heroText}>
                  {result.subject.display_name} · 围绕这件家庭小事，先试一小步，再看有没有变化
                </Text>
              </View>
            </View>

            <View
              testID="assessment-result-heard"
              style={[
                styles.card,
                { backgroundColor: colors.surface, borderColor: colors.border },
              ]}
            >
              <Text style={styles.sectionLabel}>我们听到的家庭关注</Text>
              <Text style={[styles.cardTitle, { color: colors.text }]}>
                {assessmentNeedText.trim() || result.explanation.headline}
              </Text>
              <Text style={[styles.cardText, { color: colors.muted }]}>
                {result.explanation.summary}
              </Text>
              <Text style={[styles.boundaryText, { color: colors.muted }]}>
                这是一段家庭视角的整理，不是给孩子下结论。
              </Text>
            </View>

            <View
              testID="assessment-result-directions"
              style={styles.directionCard}
            >
              <Text style={styles.sectionLabel}>可能的方向</Text>
              <Text style={styles.directionIntro}>
                {result.explanation.hypothesis}
              </Text>
              {result.explanation.recommendations
                .slice(0, 2)
                .map((recommendation) => (
                  <Text key={recommendation.text} style={styles.directionText}>
                    · {recommendation.text}
                  </Text>
                ))}
            </View>

            <View
              testID="assessment-result-uncertain"
              style={[
                styles.card,
                { backgroundColor: colors.surface, borderColor: colors.border },
              ]}
            >
              <Text style={styles.sectionLabel}>还不确定的地方</Text>
              <Text style={[styles.cardText, { color: colors.text }]}>
                这次只整理了你主动提供的少量信息；它不能代表家庭的全部情况。
              </Text>
              <Text style={[styles.cardText, { color: colors.muted }]}>
                如果上面的理解不准确，可以返回修改，或先退出，不会自动触发任何行动。
              </Text>
            </View>

            <View
              testID="assessment-result-next-step"
              style={styles.nextStepCard}
            >
              <Text style={styles.sectionLabel}>今天可以尝试的一小步</Text>
              <Text style={styles.nextStepTitle}>{firstRecommendation}</Text>
              <Text style={styles.nextStepText}>
                先做这一步，由你确认后再继续。
              </Text>
            </View>

            <View testID="assessment-result-feedback" style={styles.feedbackCard}>
              <Text style={styles.sectionLabel}>这句话像你们家吗？</Text>
              <Text style={[styles.feedbackIntro, { color: colors.text }]}>
                你的反馈会帮助我们把下一次整理说得更贴近，不会改写家庭事实。
              </Text>
              <View style={styles.feedbackRow}>
                <Pressable
                  testID="assessment-feedback-like"
                  accessibilityRole="button"
                  onPress={() => void submitPerspectiveFeedback("LIKE")}
                  style={({ pressed }) => [
                    styles.feedbackButton,
                    perspectiveFeedback === "LIKE" && styles.feedbackSelected,
                    pressed && styles.pressed,
                  ]}
                >
                  <Text style={styles.feedbackButtonText}>像我们家</Text>
                </Pressable>
                <Pressable
                  testID="assessment-feedback-not-like"
                  accessibilityRole="button"
                  onPress={() => void submitPerspectiveFeedback("NOT_LIKE")}
                  style={({ pressed }) => [
                    styles.feedbackButton,
                    perspectiveFeedback === "NOT_LIKE" && styles.feedbackSelected,
                    pressed && styles.pressed,
                  ]}
                >
                  <Text style={styles.feedbackButtonText}>不太像</Text>
                </Pressable>
                <Pressable
                  testID="assessment-feedback-add-context"
                  accessibilityRole="button"
                  onPress={() => {
                    setPerspectiveFeedback("ADD_CONTEXT");
                    setFeedbackState("idle");
                  }}
                  style={({ pressed }) => [
                    styles.feedbackButton,
                    perspectiveFeedback === "ADD_CONTEXT" && styles.feedbackSelected,
                    pressed && styles.pressed,
                  ]}
                >
                  <Text style={styles.feedbackButtonText}>补充</Text>
                </Pressable>
              </View>
              {perspectiveFeedback === "ADD_CONTEXT" ? (
                <View style={styles.supplementBox}>
                  <TextInput
                    testID="assessment-feedback-input"
                    accessibilityLabel="补充家庭情况"
                    value={supplementText}
                    onChangeText={setSupplementText}
                    placeholder="补充一句，这样的描述哪里不准确？"
                    placeholderTextColor="#94A3B8"
                    multiline
                    style={[styles.supplementInput, { color: colors.text }]}
                  />
                  <Pressable
                    testID="assessment-feedback-submit"
                    accessibilityRole="button"
                    onPress={submitSupplement}
                    style={({ pressed }) => [
                      styles.supplementSubmit,
                      pressed && styles.pressed,
                    ]}
                  >
                    <Text style={[styles.supplementSubmitText, { color: colors.tint }]}>提交补充</Text>
                  </Pressable>
                </View>
              ) : null}
              {feedbackState !== "idle" ? (
                <Text
                  accessibilityRole="alert"
                  style={[
                    styles.feedbackStatus,
                    { color: feedbackState === "retry" ? "#B42318" : colors.muted },
                  ]}
                >
                  {feedbackState === "saving"
                    ? connected
                      ? "正在保存这张支持卡的反馈…"
                      : "这次反馈只在当前页面暂存，还没有同步。"
                    : feedbackState === "retry"
                      ? "暂时无法保存反馈，请稍后重试；当前没有写入服务端。"
                      : connected
                        ? "已保存到这张家庭支持卡；它只用于修正理解，不会改写家庭事实。"
                        : "这次反馈已在当前页面暂存；你也可以返回修改刚才那句话。"}
                </Text>
              ) : null}
            </View>

            <View testID="assessment-result-action" style={styles.actionCard}>
              <Text style={styles.sectionLabel}>今晚先做一个选择</Text>
              <Pressable
                testID="assessment-start-small-step"
                accessibilityRole="button"
                disabled={smallStepState === "saving" || smallStepState === "saved"}
                onPress={() => void startSmallStep()}
                style={({ pressed }) => [
                  styles.primaryButton,
                  { backgroundColor: colors.tint },
                  pressed && styles.pressed,
                ]}
              >
                <Text style={styles.primaryButtonText}>
                  {smallStepState === "saving"
                    ? connected
                      ? "正在记下今晚这一步…"
                      : "正在暂存今晚这一步"
                    : smallStepState === "saved"
                      ? connected
                        ? "今晚就试这一步"
                        : "今晚这一步已在当前页面暂存"
                      : "开始尝试这一步"}
                </Text>
              </Pressable>
              {smallStepState === "saved" ? (
                <Text style={[styles.actionStatus, { color: colors.muted }]}>
                  {connected
                    ? "明天回来告诉我们有没有变化；这不是结果证明。"
                    : "明天可以重新打开这张家庭理解卡；本次标记还没有同步。"}
                </Text>
              ) : smallStepState === "retry" ? (
                <Text style={styles.actionError}>
                  暂时没记下，请稍后重试；不会自动触发其他行动。
                </Text>
              ) : null}
              <Pressable
                testID="assessment-save-for-later"
                accessibilityRole="button"
                onPress={saveForLater}
                style={({ pressed }) => [styles.editButton, pressed && styles.pressed]}
              >
                <Text style={[styles.editButtonText, { color: colors.tint }]}>
                  先保存，明天再看
                </Text>
              </Pressable>
            </View>

            {supportState === "error" ? (
              <View testID="assessment-support-loop-error" style={styles.notice}>
                <Text style={styles.noticeTitle}>支持卡暂时没有同步</Text>
                <Text style={styles.noticeText}>
                  你仍可以查看本次整理；重试不会重复创建反馈或今晚这一步。
                </Text>
                <Pressable
                  accessibilityRole="button"
                  onPress={() => setSupportRetryNonce((value) => value + 1)}
                  style={styles.retryButton}
                >
                  <Text style={styles.retryText}>重试同步</Text>
                </Pressable>
              </View>
            ) : null}

            {supportRemote?.small_step ? (
              <View testID="assessment-next-day-checkin" style={styles.checkinCard}>
                <Text style={styles.sectionLabel}>明天回来，告诉我们发生了什么</Text>
                <Text style={[styles.checkinIntro, { color: colors.text }]}>
                  只记录你的感受，不把一次反馈当成对孩子或家庭的结论。
                </Text>
                {supportRemote.latest_checkin ? (
                  <Text style={[styles.actionStatus, { color: colors.muted }]}>
                    已记录：
                    {supportRemote.latest_checkin.outcome === "HELPED"
                      ? "有一点帮助"
                      : supportRemote.latest_checkin.outcome === "NO_CHANGE"
                        ? "暂时没变化"
                        : "还没试"}
                    。这只是家庭反馈，不是结果证明。
                  </Text>
                ) : (
                  <>
                    <View style={styles.feedbackRow}>
                      {(
                        [
                          ["HELPED", "有一点帮助"],
                          ["NO_CHANGE", "暂时没变化"],
                          ["NOT_TRIED", "还没试"],
                        ] as const
                      ).map(([outcome, label]) => (
                        <Pressable
                          key={outcome}
                          testID={`assessment-checkin-${outcome.toLowerCase()}`}
                          accessibilityRole="button"
                          disabled={checkinState === "saving" || checkinState === "saved"}
                          onPress={() => submitCheckin(outcome)}
                          style={({ pressed }) => [
                            styles.feedbackButton,
                            checkinOutcome === outcome && styles.feedbackSelected,
                            pressed && styles.pressed,
                          ]}
                        >
                          <Text style={styles.feedbackButtonText}>{label}</Text>
                        </Pressable>
                      ))}
                    </View>
                    <TextInput
                      testID="assessment-checkin-note"
                      accessibilityLabel="补充明天的感受"
                      value={checkinNote}
                      onChangeText={setCheckinNote}
                      placeholder="想补充一句吗？（可选）"
                      placeholderTextColor="#94A3B8"
                      multiline
                      style={[styles.supplementInput, { color: colors.text }]}
                    />
                    {checkinState !== "idle" ? (
                      <Text
                        accessibilityRole="alert"
                        style={[
                          styles.feedbackStatus,
                          { color: checkinState === "retry" ? "#B42318" : colors.muted },
                        ]}
                      >
                        {checkinState === "saving"
                          ? "正在保存你的回访…"
                          : checkinState === "too_soon"
                            ? "这一步还没到回访时间，明天再回来；刚才没有写入。"
                            : checkinState === "retry"
                              ? "暂时无法保存回访，请稍后重试。"
                              : "已保存；这只是家庭反馈，不是结果证明。"}
                      </Text>
                    ) : null}
                  </>
                )}
              </View>
            ) : null}

            <Pressable
              accessibilityRole="button"
              onPress={() => setShowDetails((value) => !value)}
              style={styles.detailsToggle}
            >
              <Text style={[styles.detailsToggleText, { color: colors.tint }]}>
                {showDetails ? "收起本次依据" : "查看本次依据"}
              </Text>
              <Text style={[styles.detailsChevron, { color: colors.tint }]}>
                {showDetails ? "⌃" : "⌄"}
              </Text>
            </Pressable>
            {showDetails ? (
              <View style={styles.provenanceCard}>
                <Text style={styles.sectionLabel}>本次结果依据</Text>
                <Text style={styles.provenanceText}>
                  你刚才提供的内容：本次已提交的少量回答
                </Text>
                <Text style={styles.provenanceText}>
                  本次整理的范围：只围绕你刚才说的这件家庭小事
                </Text>
                <Text style={styles.provenanceText}>
                  仍需你确认：这是一张支持参考，是否贴近你们家由你决定
                </Text>
              </View>
            ) : null}
          </>
        )}
        <Pressable
          testID="assessment-edit"
          onPress={() => router.replace("/ui/UI-02" as Href)}
          style={({ pressed }) => [
            styles.editButton,
            pressed && styles.pressed,
          ]}
        >
          <Text style={[styles.editButtonText, { color: colors.tint }]}>
            返回修改
          </Text>
        </Pressable>
        <Pressable
          testID="assessment-restart"
          onPress={() => {
            restartAssessment();
            router.replace("/ui/UI-02" as Href);
          }}
          style={({ pressed }) => [
            styles.primaryButton,
            { backgroundColor: colors.tint },
            pressed && styles.pressed,
          ]}
        >
          <Text style={styles.primaryButtonText}>重新开始测评</Text>
        </Pressable>
        <Pressable
          testID="assessment-exit"
          onPress={() => router.back()}
          style={({ pressed }) => [
            styles.exitButton,
            pressed && styles.pressed,
          ]}
        >
          <Text style={[styles.exitText, { color: colors.muted }]}>退出</Text>
        </Pressable>
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { flexGrow: 1, padding: 18, gap: 12 },
  emptyPage: {
    flex: 1,
    minHeight: 260,
    padding: 24,
    justifyContent: "center",
    gap: 13,
  },
  emptyKicker: {
    color: "#1B65C9",
    fontSize: 13,
    lineHeight: 18,
    fontWeight: "900",
  },
  emptyTitle: { fontSize: 25, lineHeight: 33, fontWeight: "900" },
  emptyText: { fontSize: 14, lineHeight: 22 },
  notice: {
    borderRadius: 16,
    backgroundColor: "#FFF6DF",
    borderWidth: 1,
    borderColor: "#F8DE94",
    padding: 14,
    gap: 4,
  },
  noticeTitle: {
    color: "#8A5A00",
    fontSize: 14,
    lineHeight: 20,
    fontWeight: "900",
  },
  noticeText: {
    color: "#6F5A36",
    fontSize: 12,
    lineHeight: 18,
    fontWeight: "700",
  },
  retryButton: {
    alignSelf: "flex-start",
    minHeight: 32,
    justifyContent: "center",
  },
  retryText: {
    color: "#2563EB",
    fontSize: 12,
    lineHeight: 18,
    fontWeight: "900",
    textDecorationLine: "underline",
  },
  hero: {
    borderRadius: 20,
    backgroundColor: "#E8F2FF",
    padding: 16,
    gap: 12,
    flexDirection: "row",
    alignItems: "flex-start",
  },
  heroIcon: {
    width: 40,
    height: 40,
    borderRadius: 13,
    backgroundColor: "#FFFFFF",
    alignItems: "center",
    justifyContent: "center",
  },
  heroIconText: {
    color: "#1B7CF2",
    fontSize: 25,
    lineHeight: 29,
    fontWeight: "900",
  },
  heroCopy: { flex: 1, gap: 5 },
  badge: { color: "#2563EB", fontSize: 11, lineHeight: 15, fontWeight: "900" },
  heroTitle: {
    color: "#09295A",
    fontSize: 20,
    lineHeight: 27,
    fontWeight: "900",
  },
  heroText: {
    color: "#5B7091",
    fontSize: 13,
    lineHeight: 20,
    fontWeight: "700",
  },
  card: { borderRadius: 17, borderWidth: 1, padding: 16, gap: 8 },
  sectionLabel: {
    color: "#5B7091",
    fontSize: 12,
    lineHeight: 17,
    fontWeight: "900",
  },
  cardTitle: { fontSize: 18, lineHeight: 25, fontWeight: "900" },
  cardText: { fontSize: 14, lineHeight: 22 },
  boundaryText: { fontSize: 12, lineHeight: 19, marginTop: 2 },
  directionCard: {
    borderRadius: 17,
    backgroundColor: "#F7FBF8",
    borderWidth: 1,
    borderColor: "#D8EBDD",
    padding: 16,
    gap: 9,
  },
  directionIntro: {
    color: "#214B3D",
    fontSize: 15,
    lineHeight: 23,
    fontWeight: "800",
  },
  directionText: {
    color: "#214B3D",
    fontSize: 14,
    lineHeight: 22,
    fontWeight: "700",
  },
  nextStepCard: {
    borderRadius: 17,
    backgroundColor: "#FFF8ED",
    borderWidth: 1,
    borderColor: "#F2D8AA",
    padding: 16,
    gap: 8,
  },
  nextStepTitle: {
    color: "#6E4300",
    fontSize: 18,
    lineHeight: 26,
    fontWeight: "900",
  },
  nextStepText: { color: "#8A6729", fontSize: 13, lineHeight: 20 },
  feedbackCard: {
    borderRadius: 17,
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#D9E2EC",
    padding: 16,
    gap: 9,
  },
  feedbackIntro: { fontSize: 13, lineHeight: 20 },
  feedbackRow: { flexDirection: "row", gap: 8, marginTop: 2 },
  feedbackButton: {
    flex: 1,
    minHeight: 42,
    borderRadius: 13,
    borderWidth: 1,
    borderColor: "#CBD5E1",
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 6,
  },
  feedbackSelected: { backgroundColor: "#EAF2FF", borderColor: "#1B7CF2" },
  feedbackButtonText: { color: "#1B65C9", fontSize: 12, fontWeight: "900" },
  feedbackStatus: { fontSize: 12, lineHeight: 18 },
  supplementBox: { gap: 8 },
  supplementInput: {
    minHeight: 84,
    borderWidth: 1,
    borderColor: "#CBD5E1",
    borderRadius: 13,
    padding: 12,
    fontSize: 13,
    lineHeight: 20,
    textAlignVertical: "top",
  },
  supplementSubmit: {
    minHeight: 36,
    alignItems: "center",
    justifyContent: "center",
  },
  supplementSubmitText: {
    fontSize: 12,
    lineHeight: 18,
    fontWeight: "900",
    textDecorationLine: "underline",
  },
  actionCard: {
    borderRadius: 17,
    backgroundColor: "#F8FBFF",
    borderWidth: 1,
    borderColor: "#D9E8FA",
    padding: 16,
    gap: 9,
  },
  actionStatus: { fontSize: 12, lineHeight: 18 },
  actionError: { color: "#B42318", fontSize: 12, lineHeight: 18 },
  checkinCard: {
    borderRadius: 17,
    backgroundColor: "#F7F7FF",
    borderWidth: 1,
    borderColor: "#DCDCF7",
    padding: 16,
    gap: 9,
  },
  checkinIntro: { fontSize: 13, lineHeight: 20 },
  detailsToggle: {
    minHeight: 42,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
  },
  detailsToggleText: {
    fontSize: 13,
    lineHeight: 20,
    fontWeight: "900",
    textDecorationLine: "underline",
  },
  detailsChevron: { fontSize: 16, lineHeight: 20, fontWeight: "900" },
  provenanceCard: {
    borderRadius: 15,
    backgroundColor: "#F5F9FF",
    borderWidth: 1,
    borderColor: "#D9E8FA",
    padding: 14,
    gap: 5,
  },
  provenanceText: {
    color: "#5B7091",
    fontSize: 12,
    lineHeight: 18,
    fontWeight: "700",
  },
  primaryButton: {
    minHeight: 50,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 5,
  },
  editButton: {
    minHeight: 42,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  editButtonText: {
    fontSize: 13,
    lineHeight: 20,
    fontWeight: "900",
    textDecorationLine: "underline",
  },
  primaryButtonText: {
    color: "#FFFFFF",
    fontSize: 16,
    lineHeight: 22,
    fontWeight: "900",
  },
  exitButton: { minHeight: 42, alignItems: "center", justifyContent: "center" },
  exitText: {
    fontSize: 13,
    lineHeight: 20,
    fontWeight: "800",
    textDecorationLine: "underline",
  },
  pressed: { opacity: 0.82 },
});
