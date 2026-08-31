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

import { AssessmentDimensionList, AssessmentDimensionRadar } from "@/components/family/assessment-dimension-radar";
import { ScreenContainer } from "@/components/screen-container";
import { useColors } from "@/hooks/use-colors";
import type { GrowthFocusId } from "@/lib/family/core-growth";
import {
  buildAssessmentDimensionProfiles,
  getAssessmentKnowledgeBrief,
} from "@/lib/family/assessment-dimension-profile";
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
    mechanism: string | null;
    hypotheses?: {
      hypothesis_ref: string;
      text: string;
      basis: string;
      status: "DRAFT";
    }[];
    recommendations: { text: string; source: string; status: "DRAFT" }[];
  };
  dimensions?: {
    focus_ref: string;
    title: string;
    observation_status: "OBSERVED" | "NOT_YET_OBSERVED";
    observed_item_refs: string[];
  }[];
  knowledge_grounding?: {
    status: "GROUNDED" | "UNAVAILABLE";
    construct_ref: string | null;
    card_refs: string[];
    primary_card_ref?: string;
    title?: string | null;
    evidence_grade: string | null;
    core_claim: string | null;
    mechanism: string | null;
    boundary: string;
  };
  growth_plan?: {
    plan_ref: string;
    status: "DRAFT";
    goal: string;
    phases: {
      phase_ref: string;
      title: string;
      duration_days: number;
      prompt: string;
    }[];
    source_refs: string[];
    boundary: string;
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

type ConfirmedIntentReceipt = {
  action: "CONFIRM_GROWTH_HYPOTHESIS";
  outcome: "INTENT_CREATED";
  hypothesis_ref: string;
  intent: {
    intent_id: string;
    boundary: "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME";
  };
  replayed: boolean;
};

export default function GrowthExplanationScreen() {
  const colors = useColors();
  const readableSecondary = colors.background === "#0F1620" ? "#C5D2E4" : "#40556D";
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
  const [showObservationLayer, setShowObservationLayer] = useState(false);
  const [perspectiveFeedback, setPerspectiveFeedback] = useState<
    "LIKE" | "NOT_LIKE" | "ADD_CONTEXT" | null
  >(null);
  const [supplementText, setSupplementText] = useState("");
  const [feedbackState, setFeedbackState] = useState<
    "idle" | "saving" | "saved" | "retry"
  >("idle");
  const [saveState, setSaveState] = useState<"idle" | "saved">("idle");
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
  const assessmentFocus = result?.focus_ref as GrowthFocusId | null;
  const dimensionProfiles = result
    ? buildAssessmentDimensionProfiles(
        result.explanation.observations,
        assessmentFocus,
      )
    : [];
  const knowledgeBrief = getAssessmentKnowledgeBrief(assessmentFocus);
  const firstRecommendation =
    result?.explanation.recommendations[0]?.text ??
    "先把一个反复发生的时刻写进家庭方案，和孩子一起决定从哪里改变。";
  const groundedKnowledge = result?.knowledge_grounding;
  const displayedKnowledge = groundedKnowledge?.status === "GROUNDED"
    ? {
        title: groundedKnowledge.title ?? knowledgeBrief?.title ?? "家庭互动",
        familyLens: groundedKnowledge.core_claim ?? knowledgeBrief?.familyLens ?? "先看家庭互动与环境，再决定是否需要更多支持。",
        evidence: `${groundedKnowledge.primary_card_ref ?? "已审核知识参考"} · 证据等级 ${groundedKnowledge.evidence_grade ?? "待补充"}`,
        practiceThemes: knowledgeBrief?.practiceThemes ?? ["从家庭日常继续观察"],
      }
    : knowledgeBrief;
  const interpretationHypotheses = result?.explanation.hypotheses?.length
    ? result.explanation.hypotheses
    : [{
        hypothesis_ref: `${result?.assessment_session_id ?? "assessment"}:H1`,
        text: result?.explanation.hypothesis ?? "这是一份等待家庭继续确认的理解。",
        basis: "本次家庭回答",
        status: "DRAFT" as const,
      }];
  const planPhases = [
    {
      phase_ref: "RELATION_MECHANISM_7D",
      title: "关系机制",
      duration_days: 7,
      prompt: firstRecommendation,
    },
    {
      phase_ref: "COMMON_DECISION_7D",
      title: "共同决策",
      duration_days: 7,
      prompt: "把一个回应方式说清楚，和孩子一起决定什么时候、怎么试。",
    },
    {
      phase_ref: "CONFLICT_REPAIR_7D",
      title: "冲突修复",
      duration_days: 7,
      prompt: "回看一次冲突如何被修复，再一起调整下一次的家庭约定。",
    },
  ];
  const planGoal = `让「${displayedKnowledge?.title ?? result?.title ?? "家庭互动"}」回到家庭可以共同参与、共同调整的日常里。`;

  const [interpretationDecision, setInterpretationDecision] = useState<
    "idle" | "saving" | "confirmed" | "dismissed" | "retry"
  >("idle");
  const [confirmedIntentReceipt, setConfirmedIntentReceipt] =
    useState<ConfirmedIntentReceipt | null>(null);

  const keyFor = (fingerprint: string) => {
    operationKeys.current[fingerprint] ??= createMobileRequestId(
      fingerprint.replace(/[^a-z0-9]+/gi, "-").toLowerCase(),
    );
    return operationKeys.current[fingerprint];
  };

  const decideInterpretation = (decision: "CONFIRM" | "DISMISS") => {
    const hypothesis = interpretationHypotheses[0];
    if (!connected || !assessmentSessionId || !hypothesis) {
      setInterpretationDecision("retry");
      return;
    }
    setInterpretationDecision("saving");
    void familyApi
      .decideGrowthHypothesis<ConfirmedIntentReceipt | { outcome: "NO_ACTION" }>(
        session.token!,
        session.selectedFamily!.family_id,
        {
          assessment_session_id: assessmentSessionId,
          hypothesis_ref: hypothesis.hypothesis_ref,
          decision_type: decision,
        },
        keyFor(`assessment-interpretation:${assessmentSessionId}:${hypothesis.hypothesis_ref}:${decision}`),
      )
      .then((receipt: ConfirmedIntentReceipt | { outcome: "NO_ACTION" }) => {
        if (decision === "CONFIRM" && receipt.outcome === "INTENT_CREATED") {
          setConfirmedIntentReceipt(receipt);
          setInterpretationDecision("confirmed");
        } else {
          setConfirmedIntentReceipt(null);
          setInterpretationDecision("dismissed");
        }
      })
      .catch(() => setInterpretationDecision("retry"));
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

  const saveForLater = () => {
    setSaveState("saved");
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
            title: "家庭成长解读",
            headerBackTitle: "退出",
          }}
        />
        <View style={styles.emptyPage}>
          <ActivityIndicator color={colors.tint} />
          <Text style={[styles.emptyTitle, { color: colors.text }]}>
            正在整理这次家庭测评
          </Text>
          <Text style={[styles.emptyText, { color: readableSecondary }]}>
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
  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen
        options={{
          headerShown: true,
          title: "家庭成长解读",
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
            <Text style={[styles.emptyText, { color: readableSecondary }]}>
              先从一个真实家庭场景开始，完成后你会得到一张五维家庭观察画像和一份可继续修订的成长方案。
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
              <Text style={styles.primaryButtonText}>开始一次家庭成长测评</Text>
            </Pressable>
          </View>
        ) : (
          <>
            <View style={styles.hero}>
              <View style={styles.heroIcon}>
                <Text style={styles.heroIconText}>✓</Text>
              </View>
              <View style={styles.heroCopy}>
              <Text style={styles.badge}>家庭成长解读 · 家庭范围 · 可回看</Text>
              <Text style={styles.heroTitle}>
                  先看懂这一件事，再决定怎么改变
              </Text>
              <Text style={styles.heroText}>
                  {result.subject.display_name} · 从你刚才描述的真实场景出发，理解关系、习惯与环境如何彼此影响
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
              <Text style={styles.sectionLabel}>家庭理解卡 · 我们听到的家庭关注</Text>
              <Text style={[styles.cardTitle, { color: colors.text }]}>
                {assessmentNeedText.trim() || result.explanation.headline}
              </Text>
              <Text style={[styles.cardText, { color: readableSecondary }]}>
                {result.explanation.summary}
              </Text>
              <Text style={[styles.boundaryText, { color: readableSecondary }]}>
                这是一段家庭视角的整理，不是给孩子下结论。
              </Text>
              <Text style={styles.narrativeLabel}>依据</Text>
              <Text style={[styles.cardText, { color: readableSecondary }]}>本次整理只使用本次测评的回答和已标注的知识参考。</Text>
              <Text style={styles.narrativeLabel}>可能的方向</Text>
              <Text style={[styles.cardText, { color: readableSecondary }]}>以下是可继续验证的理解草案，不是诊断或事实结论。</Text>
              <Text style={styles.narrativeLabel}>还未知</Text>
              <Text style={[styles.cardText, { color: readableSecondary }]}>还需要把这份理解带回几次真实家庭时刻，才能知道哪些贴近你们家。</Text>
            </View>

            <View
              testID="assessment-result-directions"
              style={styles.directionCard}
            >
              <Text style={styles.sectionLabel}>关键机制 · 可探索方向</Text>
              <Text style={[styles.directionTitle, { color: colors.text }]}>为什么会卡在这里</Text>
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
              testID="assessment-result-knowledge"
              style={styles.knowledgeCard}
            >
              <Text style={styles.sectionLabel}>知识参考</Text>
              <Text style={styles.knowledgeTitle}>为什么先看「{displayedKnowledge?.title ?? "家庭互动"}」</Text>
              <Text style={styles.knowledgeText}>
                {displayedKnowledge?.familyLens ?? "先看家庭互动与环境，再决定是否需要更多支持。"}
              </Text>
              <View style={styles.knowledgeDivider} />
              <Text style={styles.knowledgeSource}>
                参考家庭教育与发展研究：{displayedKnowledge?.evidence ?? "这是一条家庭教育实践参考，不是对孩子的结论。"}
              </Text>
              <View style={styles.themeRow}>
                {(displayedKnowledge?.practiceThemes ?? ["从家庭日常继续观察"]).map((theme) => (
                  <View key={theme} style={styles.themeChip}>
                    <Text style={styles.themeChipText}>{theme}</Text>
                  </View>
                ))}
              </View>
            </View>

            <View
              testID="assessment-result-interpretation"
              style={styles.interpretationCard}
            >
              <Text style={styles.sectionLabel}>家庭成长解读</Text>
              <Text style={[styles.interpretationTitle, { color: colors.text }]}>先提出几种可能，再由你来判断</Text>
              <Text style={[styles.cardText, { color: readableSecondary }]}>
                {result.ai.model_gateway_status === "DRAFT"
                  ? "AI 已根据本次回答和知识参考整理出一份初稿。"
                  : "这份解读先根据你的回答和知识参考整理出来，哪些贴近你们家，由你来判断。"}
              </Text>
              {interpretationHypotheses.map((hypothesis, index) => (
                <View key={hypothesis.hypothesis_ref} style={styles.interpretationQuote}>
                  <Text style={styles.interpretationQuoteLabel}>{index === 0 ? "当前理解" : "另一种可能"}</Text>
                  <Text style={[styles.interpretationQuoteText, { color: colors.text }]}>
                    {hypothesis.text}
                  </Text>
                  <Text style={styles.hypothesisBasis}>依据：{hypothesis.basis}</Text>
                </View>
              ))}
              {result.explanation.mechanism ? (
                <Text style={[styles.cardText, { color: readableSecondary }]}>可能的关系机制：{result.explanation.mechanism}</Text>
              ) : null}
              <Text style={[styles.boundaryText, { color: readableSecondary }]}>你可以确认、补充或否定这份理解；不贴近你们家的部分，就停在这里。</Text>
              <View testID="assessment-human-gate" style={styles.humanGate}>
                <Text style={styles.humanGateTitle}>由你决定要不要把它带回家庭</Text>
                <Text style={[styles.humanGateText, { color: readableSecondary }]}>
                  确认后才会记录为这次家庭关注；拒绝不会创建后续方案。
                </Text>
                <View style={styles.feedbackRow}>
                  <Pressable
                    accessibilityRole="button"
                    testID="assessment-hypothesis-confirm"
                    disabled={interpretationDecision === "saving" || interpretationDecision === "confirmed"}
                    onPress={() => decideInterpretation("CONFIRM")}
                    style={({ pressed }) => [
                      styles.gatePrimary,
                      interpretationDecision === "confirmed" && styles.gatePrimaryConfirmed,
                      interpretationDecision === "saving" && styles.gatePrimaryDisabled,
                      pressed && styles.pressed,
                    ]}
                  >
                    <Text style={styles.gatePrimaryText}>
                      {interpretationDecision === "saving" ? "正在记录…" : "确认这份理解"}
                    </Text>
                  </Pressable>
                  <Pressable
                    accessibilityRole="button"
                    testID="assessment-hypothesis-dismiss"
                    disabled={interpretationDecision === "saving" || interpretationDecision === "dismissed"}
                    onPress={() => decideInterpretation("DISMISS")}
                    style={({ pressed }) => [
                      styles.gateSecondary,
                      interpretationDecision === "dismissed" && styles.gateSecondaryDismissed,
                      interpretationDecision === "saving" && styles.gateSecondaryDisabled,
                      pressed && styles.pressed,
                    ]}
                  >
                    <Text style={styles.gateSecondaryText}>暂不采用</Text>
                  </Pressable>
                </View>
                {interpretationDecision !== "idle" ? (
                  <Text
                    accessibilityRole="alert"
                    style={[
                      styles.feedbackStatus,
                      { color: interpretationDecision === "retry" ? "#B42318" : readableSecondary },
                    ]}
                  >
                    {interpretationDecision === "confirmed"
                      ? "已按你的确认记录这次家庭关注；是否继续形成方案，由你决定。"
                      : interpretationDecision === "dismissed"
                        ? "已暂不采用这份理解；没有创建后续方案。"
                        : interpretationDecision === "retry"
                          ? "暂时无法记录你的选择，请稍后重试。"
                          : "正在记录你的选择…"}
                  </Text>
                ) : null}
                {confirmedIntentReceipt ? (
                  <View testID="assessment-confirmed-intent-receipt" style={styles.receiptBox}>
                    <Text style={styles.receiptTitle}>已生成家庭关注确认凭据</Text>
                    <Text style={[styles.receiptText, { color: readableSecondary }]}>编号：{confirmedIntentReceipt.intent.intent_id}</Text>
                    <Text style={[styles.receiptText, { color: readableSecondary }]}>这是你确认的关注，不是诊断或结果；后续方案仍需由你决定。</Text>
                  </View>
                ) : null}
              </View>
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
                一次测评只能照见此刻的一个切面；真正重要的，是把它带回几次真实的家庭时刻里继续看。
              </Text>
              <Text style={[styles.cardText, { color: readableSecondary }]}>
                如果上面的理解不准确，可以返回修改；你也可以先停在这里，不必急着做决定。
              </Text>
            </View>

            <View testID="assessment-result-profile" style={styles.profileSection}>
              <View style={styles.sectionHeadingRow}>
                <View style={styles.sectionHeadingCopy}>
                  <Text style={styles.sectionLabel}>观察层与复盘 · 家庭观察画像</Text>
                  <Text style={[styles.sectionTitle, { color: colors.text }]}>五个方向，组成一张家庭地图</Text>
                </View>
                <Pressable
                  accessibilityRole="button"
                  testID="assessment-observation-toggle"
                  onPress={() => setShowObservationLayer((value) => !value)}
                  style={styles.editButton}
                >
                  <Text style={[styles.editButtonText, { color: colors.tint }]}>{showObservationLayer ? "收起" : "查看"}</Text>
                </Pressable>
              </View>
              <Text style={[styles.directionHint, { marginTop: 0 }]}>这里只回看本次回答留下的线索，不是分数、排名或对孩子的结论。</Text>
              {showObservationLayer ? (
                <View testID="assessment-observation-layer">
                  <AssessmentDimensionRadar profiles={dimensionProfiles} />
                  <AssessmentDimensionList
                    profiles={dimensionProfiles}
                    activeFocus={assessmentFocus}
                  />
                </View>
              ) : null}
            </View>

            <View testID="assessment-result-next-step" style={styles.planCard}>
              <View style={styles.sectionHeadingRow}>
                <View style={styles.sectionHeadingCopy}>
                  <Text style={styles.sectionLabel}>家庭成长方案</Text>
                  <Text style={[styles.planTitle, { color: colors.text }]}>从理解走向持续改变</Text>
                </View>
                <Text style={styles.planBadge}>可修订</Text>
              </View>
              <Text style={[styles.planGoal, { color: colors.text }]}>目标：{planGoal}</Text>
              <View style={styles.planTimeline}>
                {planPhases.map((phase, index) => (
                  <View key={phase.phase_ref} style={styles.planPhase}>
                  <Text style={styles.planPhaseDay}>{index === 0 ? "第 1–7 天" : index === 1 ? "第 8–14 天" : "第 15–21 天"}</Text>
                    <Text style={styles.planPhaseTitle}>{phase.title}</Text>
                    <Text style={styles.planPhaseText}>{phase.prompt}</Text>
                  </View>
                ))}
              </View>
              <Text style={styles.nextStepText}>先确认目标，再按你们家的节奏走过三个阶段；每一阶段都可以调整。</Text>
            </View>

            <View testID="assessment-result-feedback" style={styles.feedbackCard}>
              <Text style={styles.sectionLabel}>由你来定，这份理解对不对</Text>
              <Text
                style={[styles.feedbackIntro, { color: colors.text }]}
              >
                你最了解自己的家庭。确认、修订或补充，会让下一阶段真正贴近你们的生活。
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
                      ? "正在记下你的反馈…"
                      : "这次反馈还没有放入家庭空间，登录后可以继续校准。"
                    : feedbackState === "retry"
                      ? "暂时无法保存反馈，请稍后重试；当前没有写入服务端。"
                      : connected
                        ? "已保存你的校准；它只用于修正理解，不会改写家庭事实。"
                        : "这次反馈已记在本次整理里；你也可以返回修改刚才那句话。"}
                </Text>
              ) : null}
            </View>

            <View testID="assessment-result-action" style={styles.actionCard}>
              <Text style={styles.sectionLabel}>家庭决定 · 进入 21 天计划</Text>
              <Text style={[styles.actionTitle, { color: colors.text }]}>确认这份理解后，再一起走过三个家庭机制阶段</Text>
              <Text style={[styles.cardText, { color: readableSecondary }]}>关系机制、共同决策、冲突修复都以家庭自己的观察和复盘为依据；不会自动创建行动。</Text>
              {interpretationDecision === "confirmed" ? (
                <Pressable
                  accessibilityRole="button"
                  testID="assessment-open-journey-plan"
                  onPress={() => router.push("/ui/UI-04" as Href)}
                  style={({ pressed }) => [styles.primaryButton, { backgroundColor: colors.tint }, pressed && styles.pressed]}
                >
                  <Text style={styles.primaryButtonText}>进入 21 天家庭计划</Text>
                </Pressable>
              ) : (
                <Text style={styles.actionError}>请先在上方确认这份理解，确认后才可以进入家庭计划。</Text>
              )}
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
              {saveState === "saved" ? <Text style={[styles.actionStatus, { color: readableSecondary }]}>已保存当前理解，回来后仍可修改或确认。</Text> : null}
            </View>

            {supportState === "error" ? (
              <View testID="assessment-support-loop-error" style={styles.notice}>
                <Text style={styles.noticeTitle}>成长方案暂时没有更新</Text>
                <Text style={styles.noticeText}>
                  你仍可以查看本次解读；重新更新不会重复创建校准或方案阶段。
                </Text>
                <Pressable
                  accessibilityRole="button"
                  onPress={() => setSupportRetryNonce((value) => value + 1)}
                  style={styles.retryButton}
                >
                  <Text style={styles.retryText}>重新更新</Text>
                </Pressable>
              </View>
            ) : null}

            {supportRemote?.small_step ? (
              <View testID="assessment-next-day-checkin" style={styles.checkinCard}>
                <Text style={styles.sectionLabel}>阶段复盘</Text>
                <Text style={[styles.checkinIntro, { color: colors.text }]}>
                  回到真实生活里，看见发生了什么，再决定方案是否需要调整。
                </Text>
                {supportRemote.latest_checkin ? (
                  <Text style={[styles.actionStatus, { color: readableSecondary }]}>
                    已记录：
                    {supportRemote.latest_checkin.outcome === "HELPED"
                      ? "有一点帮助"
                      : supportRemote.latest_checkin.outcome === "NO_CHANGE"
                        ? "暂时没变化"
                        : "还没试"}
                    。这是家庭复盘，不是结果证明。
                  </Text>
                ) : (
                  <>
                    <View style={styles.feedbackRow}>
                      {(
                        [
                          ["HELPED", "更顺了一点"],
                          ["NO_CHANGE", "还没有变化"],
                          ["NOT_TRIED", "还没开始"],
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
                          ? "正在保存阶段复盘…"
                          : checkinState === "too_soon"
                            ? "这一步还没到回访时间，明天再回来；刚才没有写入。"
                            : checkinState === "retry"
                              ? "暂时无法保存复盘，请稍后重试。"
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
                  本次整理的范围：只围绕你刚才描述的家庭处境
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
          <Text style={[styles.exitText, { color: readableSecondary }]}>退出</Text>
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
  profileSection: { gap: 10 },
  sectionHeadingRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 10,
  },
  sectionHeadingCopy: { flex: 1, gap: 3 },
  sectionTitle: { fontSize: 18, lineHeight: 25, fontWeight: "900" },
  sectionMeta: { color: "#7B8FA4", fontSize: 11, lineHeight: 17, fontWeight: "800" },
  card: { borderRadius: 17, borderWidth: 1, padding: 16, gap: 8 },
  sectionLabel: {
    color: "#5B7091",
    fontSize: 12,
    lineHeight: 17,
    fontWeight: "900",
  },
  cardTitle: { fontSize: 18, lineHeight: 25, fontWeight: "900" },
  cardText: { fontSize: 14, lineHeight: 22 },
  narrativeLabel: { color: "#2563EB", fontSize: 11, lineHeight: 16, fontWeight: "900", marginTop: 2 },
  boundaryText: { fontSize: 12, lineHeight: 19, marginTop: 2 },
  directionCard: {
    borderRadius: 17,
    backgroundColor: "#F7FBF8",
    borderWidth: 1,
    borderColor: "#D8EBDD",
    padding: 16,
    gap: 9,
  },
  directionTitle: { fontSize: 18, lineHeight: 25, fontWeight: "900" },
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
  directionHint: { color: "#5B7091", fontSize: 12, lineHeight: 18 },
  knowledgeCard: {
    borderRadius: 18,
    backgroundColor: "#FFFDF8",
    borderWidth: 1,
    borderColor: "#F0E2C4",
    padding: 16,
    gap: 9,
  },
  knowledgeTitle: { color: "#4A3514", fontSize: 17, lineHeight: 24, fontWeight: "900" },
  knowledgeText: { color: "#624B22", fontSize: 14, lineHeight: 22, fontWeight: "700" },
  knowledgeDivider: { height: 1, backgroundColor: "#F1E7D2" },
  knowledgeSource: { color: "#6A501C", fontSize: 12, lineHeight: 18 },
  themeRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  themeChip: { borderRadius: 10, backgroundColor: "#FFF2D6", paddingHorizontal: 9, paddingVertical: 5 },
  themeChipText: { color: "#76551C", fontSize: 11, lineHeight: 16, fontWeight: "900" },
  interpretationCard: {
    borderRadius: 18,
    backgroundColor: "#F7F5FF",
    borderWidth: 1,
    borderColor: "#DED9F7",
    padding: 16,
    gap: 9,
  },
  interpretationTitle: { fontSize: 18, lineHeight: 25, fontWeight: "900" },
  interpretationQuote: {
    borderRadius: 14,
    backgroundColor: "#FFFFFF",
    borderLeftWidth: 3,
    borderLeftColor: "#7665D8",
    padding: 12,
    gap: 5,
  },
  interpretationQuoteLabel: { color: "#7665D8", fontSize: 11, lineHeight: 16, fontWeight: "900" },
  interpretationQuoteText: { fontSize: 15, lineHeight: 23, fontWeight: "800" },
  hypothesisBasis: { color: "#7D769F", fontSize: 11, lineHeight: 17 },
  humanGate: { borderRadius: 15, backgroundColor: "#FFFFFF", padding: 12, gap: 7 },
  humanGateTitle: { color: "#2A245B", fontSize: 14, lineHeight: 20, fontWeight: "900" },
  humanGateText: { fontSize: 12, lineHeight: 18 },
  receiptBox: { borderRadius: 12, backgroundColor: "#ECFDF3", padding: 10, gap: 3 },
  receiptTitle: { color: "#176B45", fontSize: 12, lineHeight: 17, fontWeight: "900" },
  receiptText: { fontSize: 11, lineHeight: 17 },
  gatePrimary: { flex: 1, minHeight: 40, borderRadius: 13, backgroundColor: "#7665D8", alignItems: "center", justifyContent: "center", paddingHorizontal: 8 },
  gatePrimaryConfirmed: { backgroundColor: "#2E7D61" },
  gatePrimaryDisabled: { backgroundColor: "#8293A6", opacity: 1 },
  gatePrimaryText: { color: "#FFFFFF", fontSize: 12, lineHeight: 17, fontWeight: "900" },
  gateSecondary: { flex: 1, minHeight: 40, borderRadius: 13, borderWidth: 1, borderColor: "#C9C2EE", alignItems: "center", justifyContent: "center", paddingHorizontal: 8 },
  gateSecondaryDismissed: { backgroundColor: "#E8EDF3", borderColor: "#9EADBD" },
  gateSecondaryDisabled: { backgroundColor: "#F0F3F6", borderColor: "#AAB7C5", opacity: 1 },
  gateSecondaryText: { color: "#5C4DB0", fontSize: 12, lineHeight: 17, fontWeight: "900" },
  planCard: {
    borderRadius: 19,
    backgroundColor: "#F4FBF7",
    borderWidth: 1,
    borderColor: "#CFE7D8",
    padding: 16,
    gap: 10,
  },
  planTitle: { fontSize: 19, lineHeight: 26, fontWeight: "900" },
  planBadge: { color: "#2C7B5D", backgroundColor: "#DDF3E6", borderRadius: 10, paddingHorizontal: 8, paddingVertical: 4, fontSize: 11, lineHeight: 16, fontWeight: "900" },
  planGoal: { fontSize: 14, lineHeight: 22, fontWeight: "800" },
  planTimeline: { gap: 8 },
  planPhase: { borderRadius: 14, backgroundColor: "#FFFFFF", padding: 12, gap: 3 },
  planPhaseDay: { color: "#2C7B5D", fontSize: 11, lineHeight: 16, fontWeight: "900" },
  planPhaseTitle: { color: "#173D2E", fontSize: 15, lineHeight: 21, fontWeight: "900" },
  planPhaseText: { color: "#4E6A5A", fontSize: 13, lineHeight: 20 },
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
  actionTitle: { fontSize: 16, lineHeight: 23, fontWeight: "900" },
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
