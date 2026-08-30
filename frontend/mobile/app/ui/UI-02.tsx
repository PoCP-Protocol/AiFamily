import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import type { AssessmentAnswer, GrowthFocusId } from "@/lib/family/core-growth";
import {
  UI02_ASSESSMENT_ANSWER_OPTIONS,
  buildUi02AssessmentQuestionPlan,
  type Ui02AssessmentAnswer,
} from "@/lib/family/ui02-assessment-design";
import { UI02_ORIGINAL_FOCUS_LAYOUT } from "@/lib/family/ui02-assessment-layout";
import {
  createMobileRequestId,
  familyApi,
} from "@/lib/family/family-api-client";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";
import { haptic } from "@/lib/haptics";

type RemoteAssessmentSession = {
  assessment_session_id: string;
  subject_person_id: string;
  tool_ref: string;
  tool_version: number;
  row_version: number;
  status: "IN_PROGRESS" | "SUBMITTED" | "EXITED";
  responses: {
    item_ref: string;
    response_value: string | boolean;
    revision: number;
  }[];
};

type RemoteAssessmentProjection = {
  projection_version: "UI02_FAMILY_ASSESSMENT_V1";
  availability:
    | "AVAILABLE"
    | "CONSENT_REQUIRED"
    | "NO_SUBJECT"
    | "POLICY_BLOCKED";
  subjects: {
    person_id: string;
    display_name: string;
    availability: "AVAILABLE" | "CONSENT_REQUIRED";
  }[];
  tool: {
    tool_ref: string;
    version_no: number;
    title: string;
    purpose: string;
    evidence_level: "E1";
    boundary: { not_a_score: true; not_a_diagnosis: true; training_use: false };
  } | null;
  sessions: RemoteAssessmentSession[];
};

type AssessmentReceipt = {
  session: RemoteAssessmentSession;
  replayed: boolean;
  evidence_id?: string;
};
type FlowStep = "story" | "consent" | "focus" | "questions";
type VoiceRecognition = {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: (event: {
    results: { [index: number]: { [index: number]: { transcript: string } } };
  }) => void;
  onerror: () => void;
  onend: () => void;
  start: () => void;
};
type VoiceWindow = Window & {
  SpeechRecognition?: new () => VoiceRecognition;
  webkitSpeechRecognition?: new () => VoiceRecognition;
};

const ASSESSMENT_BOUNDARY_TEXT = "这是家庭自查，不给孩子打分，不做诊断或排名。";
const STEP_LABELS: Record<FlowStep, string> = {
  story: "说说来意",
  consent: "说明用途",
  focus: "确认理解",
  questions: "看见日常",
};

const STARTER_SCENES = [
  ["写作业总吵", "一到写作业就容易吵起来"],
  ["手机放不下", "孩子总想继续玩手机，停下来很难"],
  ["早上总催促", "每天早上都在催，家里很累"],
] as const;

const INTERNAL_FOCUS_RULES: {
  focus: GrowthFocusId;
  keywords: string[];
}[] = [
  {
    focus: "LEARNING_HABITS",
    keywords: ["作业", "学习", "写字", "阅读", "拖拉", "磨蹭"],
  },
  {
    focus: "EMOTION_REGULATION",
    keywords: ["情绪", "生气", "发脾气", "哭", "焦虑", "崩溃"],
  },
  {
    focus: "DEVICE_USE_CONTEXT",
    keywords: ["手机", "平板", "游戏", "屏幕", "短视频", "上网"],
  },
  {
    focus: "SELF_REGULATION",
    keywords: ["自律", "坚持", "时间", "习惯", "收拾", "规划"],
  },
  {
    focus: "PARENT_CHILD_COMMUNICATION",
    keywords: ["沟通", "吵", "争吵", "说话", "亲子", "不听"],
  },
];
const INTERNAL_FOCUS_UNKNOWN: GrowthFocusId = "PARENT_CHILD_COMMUNICATION";

// This is a routing heuristic only: it selects a small question set. 仅用于选择少量问题，
// 不会生成家庭理解、事实或解释，也不写入 canonical Fact；
// ambiguous or unknown wording uses the neutral fallback without claiming
// that the fallback is an interpretation of the family's situation.
function inferInternalFocus(needText: string): GrowthFocusId {
  const normalized = needText.trim().toLowerCase();
  return (
    INTERNAL_FOCUS_RULES.find((rule) =>
      rule.keywords.some((keyword) => normalized.includes(keyword)),
    )?.focus ?? INTERNAL_FOCUS_UNKNOWN
  );
}

export default function FamilyAssessmentScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const {
    selectedGrowthFocus,
    assessmentNeedText,
    assessmentFlowStep,
    assessmentAnswers,
    assessmentSyncState,
    answerAssessment,
    saveAssessmentNeed,
    selectGrowthFocus,
    setAssessmentStep,
    setAssessmentSyncState,
  } = useFamilyMobile();
  const [boundaryAccepted, setBoundaryAccepted] = useState(false);
  const [projection, setProjection] =
    useState<RemoteAssessmentProjection | null>(null);
  const [projectionState, setProjectionState] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [subjectId, setSubjectId] = useState<string | null>(null);
  const [questionIndex, setQuestionIndex] = useState(0);
  const [submissionError, setSubmissionError] = useState<string | null>(null);
  const [voiceState, setVoiceState] = useState<
    "idle" | "listening" | "unsupported"
  >("idle");
  const retryKeys = useRef<Record<string, string>>({});

  const flowStep = (assessmentFlowStep ?? "story") as FlowStep;
  const selectedFocusId = selectedGrowthFocus as GrowthFocusId | null;
  const assessmentQuestions = buildUi02AssessmentQuestionPlan(selectedFocusId);
  const currentQuestion = assessmentQuestions[questionIndex];
  const currentAnswer = currentQuestion
    ? assessmentAnswers[currentQuestion.itemRef]
    : undefined;
  const connected =
    session.status === "connected" &&
    !!session.token &&
    !!session.selectedFamily;
  const remoteCanStart = !connected || projection?.availability === "AVAILABLE";
  const displayNeed = (assessmentNeedText ?? "").trim();
  const reflectedNeed = displayNeed
    ? `我听到你想先把“${displayNeed.length > 46 ? `${displayNeed.slice(0, 46)}…` : displayNeed}”这个家庭处境看清，不急着给孩子下结论。`
    : "我听到你想先找到一个少一点冲突、可以从今天开始的家庭小办法。";

  const keyFor = (fingerprint: string) => {
    retryKeys.current[fingerprint] ??= createMobileRequestId(
      fingerprint.replace(/[^a-z0-9]+/gi, "-").toLowerCase(),
    );
    return retryKeys.current[fingerprint];
  };

  const loadAssessment = useCallback(async () => {
    if (!connected) {
      setProjection(null);
      setProjectionState("idle");
      return;
    }
    setProjectionState("loading");
    try {
      const next =
        await familyApi.getFamilyAssessment<RemoteAssessmentProjection>(
          session.token!,
          session.selectedFamily!.family_id,
        );
      setProjection(next);
      setProjectionState("ready");
    } catch {
      setProjectionState("error");
    }
  }, [connected, session.selectedFamily, session.token]);

  useEffect(() => {
    void loadAssessment();
  }, [loadAssessment]);

  useEffect(() => {
    const available =
      projection?.subjects.filter(
        (subject) => subject.availability === "AVAILABLE",
      ) ?? [];
    setSubjectId((current) =>
      current && available.some((subject) => subject.person_id === current)
        ? current
        : (available[0]?.person_id ?? null),
    );
  }, [projection]);

  useEffect(() => {
    if (!projection || !subjectId) return;
    const active = projection.sessions.find(
      (item) =>
        item.subject_person_id === subjectId && item.status === "IN_PROGRESS",
    );
    const focus = active?.responses.find(
      (item) => item.item_ref === "FOCUS",
    )?.response_value;
    if (
      typeof focus === "string" &&
      UI02_ORIGINAL_FOCUS_LAYOUT.some((item) => item.id === focus)
    )
      selectGrowthFocus(focus as GrowthFocusId);
    if (active) {
      const answerIds = new Set(
        UI02_ASSESSMENT_ANSWER_OPTIONS.map((option) => option.id),
      );
      for (const response of active.responses) {
        if (
          typeof response.response_value === "string" &&
          answerIds.has(response.response_value as Ui02AssessmentAnswer)
        ) {
          answerAssessment(
            response.item_ref,
            response.response_value as AssessmentAnswer,
          );
        }
      }
    }
  }, [answerAssessment, projection, selectGrowthFocus, subjectId]);

  useEffect(() => {
    if (flowStep === "questions" && assessmentQuestions.length === 0)
      setAssessmentStep("focus");
    if (
      questionIndex >= assessmentQuestions.length &&
      assessmentQuestions.length > 0
    )
      setQuestionIndex(0);
  }, [
    assessmentQuestions.length,
    flowStep,
    questionIndex,
    setAssessmentStep,
  ]);

  const saveFocus = async () => {
    // A restored draft is already past the plain-language consent step. The
    // backend remains the source of truth and re-checks canonical consent on
    // every connected write; this only prevents a local component reset from
    // making the final action silently inert after resume.
    const consentStepCompleted = boundaryAccepted || flowStep === "questions";
    if (!selectedFocusId || !consentStepCompleted) return;
    haptic.light();
    if (connected) {
      if (
        !projection ||
        projection.availability !== "AVAILABLE" ||
        !projection.tool ||
        !subjectId
      ) {
        setSubmissionError(
          "当前家庭还没有可用的测评授权；你可以保留草稿，稍后再来。",
        );
        return;
      }
      try {
        setAssessmentSyncState("syncing");
        setSubmissionError(null);
        const familyId = session.selectedFamily!.family_id;
        const active = projection.sessions.find(
          (item) =>
            item.subject_person_id === subjectId &&
            item.status === "IN_PROGRESS",
        );
        const started = active
          ? { session: active }
          : await familyApi.startFamilyAssessment<AssessmentReceipt>(
              session.token!,
              familyId,
              {
                subject_person_id: subjectId,
                tool_ref: projection.tool.tool_ref,
              },
              keyFor(
                `ui02-start:${familyId}:${subjectId}:${projection.tool.tool_ref}`,
              ),
            );
        const sessionId = started.session.assessment_session_id;
        const focusReceipt =
          await familyApi.saveFamilyAssessmentResponse<AssessmentReceipt>(
            session.token!,
            familyId,
            sessionId,
            {
              item_ref: "FOCUS",
              response_type: "SINGLE_CHOICE",
              response_value: selectedFocusId,
            },
            keyFor(`ui02-focus:${sessionId}:${selectedFocusId}`),
          );
        for (const question of assessmentQuestions) {
          const answer = assessmentAnswers[question.itemRef];
          if (answer) {
            await familyApi.saveFamilyAssessmentResponse<AssessmentReceipt>(
              session.token!,
              familyId,
              sessionId,
              {
                item_ref: question.itemRef,
                response_type: "SINGLE_CHOICE",
                response_value: answer,
              },
              keyFor(
                `ui02-question:${sessionId}:${question.itemRef}:${answer}`,
              ),
            );
          }
        }
        const submitted =
          await familyApi.submitFamilyAssessment<AssessmentReceipt>(
            session.token!,
            familyId,
            sessionId,
            keyFor(
              `ui02-submit:${sessionId}:${focusReceipt.session.row_version}`,
            ),
          );
        setProjection((current) =>
          current
            ? {
                ...current,
                sessions: [
                  submitted.session,
                  ...current.sessions.filter(
                    (item) => item.assessment_session_id !== sessionId,
                  ),
                ],
              }
            : current,
        );
        setAssessmentSyncState("synced");
      } catch {
        setAssessmentSyncState("error");
        setSubmissionError(
          "暂时没有提交成功；可以安全重试，不会重复创建记录。",
        );
        return;
      }
    } else {
      setAssessmentSyncState("local");
    }
    setAssessmentStep("questions");
    haptic.success();
    router.push(
      (connected ? "/ui/UI-03" : "/ui/UI-02-result") as Href,
    );
  };

  const leaveWithDraft = () => {
    setAssessmentStep(flowStep);
    router.back();
  };

  const continueStory = () => setAssessmentStep("consent");

  const startVoiceSandbox = () => {
    const voiceWindow =
      typeof window === "undefined" ? null : (window as VoiceWindow);
    const Recognition =
      voiceWindow?.SpeechRecognition ?? voiceWindow?.webkitSpeechRecognition;
    if (!Recognition) {
      setVoiceState("unsupported");
      return;
    }
    const recognition = new Recognition();
    recognition.lang = "zh-CN";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event) => {
      const transcript = event.results[0]?.[0]?.transcript?.trim();
      if (transcript) saveAssessmentNeed(transcript);
      setVoiceState("idle");
    };
    recognition.onerror = () => setVoiceState("unsupported");
    recognition.onend = () =>
      setVoiceState((state) => (state === "listening" ? "idle" : state));
    setVoiceState("listening");
    recognition.start();
  };

  const continueConsent = () => {
    if (!remoteCanStart) return;
    setBoundaryAccepted(true);
    selectGrowthFocus(inferInternalFocus(displayNeed));
    setQuestionIndex(0);
    setAssessmentStep("focus");
  };

  const continueQuestion = () => {
    if (!currentQuestion) return;
    if (!currentAnswer) {
      setSubmissionError("可以选择一个答案，也可以按“跳过这一题”。");
      return;
    }
    setSubmissionError(null);
    if (questionIndex < assessmentQuestions.length - 1)
      setQuestionIndex((value) => value + 1);
    else void saveFocus();
  };

  const skipQuestion = () => {
    setSubmissionError(null);
    if (questionIndex < assessmentQuestions.length - 1)
      setQuestionIndex((value) => value + 1);
    else void saveFocus();
  };

  return (
    <ScreenContainer edges={["top", "left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView
        refreshControl={<FamilyRefreshControl />}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.topBar}>
          <Pressable
            accessibilityLabel="返回"
            onPress={leaveWithDraft}
            hitSlop={10}
            style={styles.backButton}
          >
            <Text style={[styles.backArrow, { color: colors.text }]}>‹</Text>
          </Pressable>
          <Text style={[styles.screenTitle, { color: colors.text }]}>
            家庭成长测评
          </Text>
          <Text style={[styles.saveTop, { color: colors.muted }]}>可保存</Text>
        </View>
        <View style={styles.progressBlock}>
          <View style={styles.progressLabels}>
            <Text style={[styles.progressStep, { color: colors.text }]}>
              {STEP_LABELS[flowStep]}
            </Text>
            <Text style={[styles.progressHint, { color: colors.muted }]}>
              你可以随时返回
            </Text>
          </View>
          <View
            style={[styles.progressTrack, { backgroundColor: colors.border }]}
          >
            <View
              style={[
                styles.progressValue,
                {
                  backgroundColor: "#1B7CF2",
                  width: `${((Object.keys(STEP_LABELS).indexOf(flowStep) + 1) / 4) * 100}%`,
                },
              ]}
            />
          </View>
        </View>
        {flowStep === "story" ? (
          <StoryStep
            colors={colors}
            value={assessmentNeedText ?? ""}
            voiceState={voiceState}
            onVoice={startVoiceSandbox}
            onChange={saveAssessmentNeed}
            onContinue={continueStory}
            onSave={leaveWithDraft}
          />
        ) : null}
        {flowStep === "consent" ? (
          <ConsentStep
            colors={colors}
            projectionState={projectionState}
            availability={projection?.availability}
            remoteCanStart={remoteCanStart}
            onBack={() => setAssessmentStep("story")}
            onContinue={continueConsent}
            onExit={leaveWithDraft}
            onRetry={() => void loadAssessment()}
          />
        ) : null}
        {flowStep === "focus" ? (
          <ReflectionStep
            colors={colors}
            needText={reflectedNeed}
            selectedFocusId={selectedFocusId}
            onSelectFocus={selectGrowthFocus}
            onBack={() => setAssessmentStep("consent")}
            onContinue={() => {
              setAssessmentStep("questions");
              setQuestionIndex(0);
            }}
            onCorrect={() => setAssessmentStep("story")}
            onSave={leaveWithDraft}
          />
        ) : null}
        {flowStep === "questions" && currentQuestion ? (
          <QuestionStep
            colors={colors}
            index={questionIndex}
            total={assessmentQuestions.length}
            dimensionTitle={currentQuestion.focusTitle}
            depth={currentQuestion.depth}
            question={currentQuestion.text}
            selectedAnswer={currentAnswer as Ui02AssessmentAnswer | undefined}
            onBack={() =>
              questionIndex > 0
                ? setQuestionIndex((value) => value - 1)
                : setAssessmentStep("focus")
            }
            onAnswer={(answer) => {
              answerAssessment(currentQuestion.itemRef, answer);
              setSubmissionError(null);
            }}
            onSkip={skipQuestion}
            onContinue={continueQuestion}
            saving={assessmentSyncState === "syncing"}
          />
        ) : null}
        {submissionError ? (
          <Text accessibilityRole="alert" style={styles.errorText}>
            {submissionError}
          </Text>
        ) : null}
        {connected && projectionState === "loading" ? (
          <View style={styles.loadingRow}>
            <ActivityIndicator color={colors.tint} />
            <Text style={[styles.loadingText, { color: colors.muted }]}>
              正在确认家庭授权…
            </Text>
          </View>
        ) : null}
      </ScrollView>
    </ScreenContainer>
  );
}

function StoryStep({
  colors,
  value,
  voiceState,
  onVoice,
  onChange,
  onContinue,
  onSave,
}: {
  colors: ReturnType<typeof useColors>;
  value: string;
  voiceState: "idle" | "listening" | "unsupported";
  onVoice: () => void;
  onChange: (value: string) => void;
  onContinue: () => void;
  onSave: () => void;
}) {
  return (
    <View style={styles.stepContent}>
      <View style={[styles.eyebrow, { backgroundColor: "#EEF6FF" }]}>
        <IconSymbol name="heart.fill" size={16} color="#1B7CF2" />
        <Text style={styles.eyebrowText}>从真实家庭处境开始</Text>
      </View>
      <Text style={[styles.title, { color: colors.text }]}>
        你希望家庭先看清什么？
      </Text>
      <Text style={[styles.subtitle, { color: colors.muted }]}>
        用你自己的话说出最近反复出现的场景。不用先判断谁对谁错，也不用把事情讲完整。
      </Text>
      <View style={styles.storyPromise}>
        <Text style={styles.storyPromiseTitle}>3 分钟后，你会带走</Text>
        <View style={styles.storyPromiseRow}>
          <Text style={styles.storyPromiseItem}>一张五维家庭画像</Text>
          <Text style={styles.storyPromiseDot}>·</Text>
          <Text style={styles.storyPromiseItem}>一份可继续修订的成长方案</Text>
        </View>
      </View>
      <View style={styles.sceneStarterBlock}>
        <Text style={[styles.sceneStarterLabel, { color: colors.muted }]}>
          不知道怎么开始？先选一个最像的
        </Text>
        <View style={styles.sceneStarterRow}>
          {STARTER_SCENES.map(([label, text]) => (
            <Pressable
              key={label}
              testID={`assessment-scene-${label}`}
              accessibilityRole="button"
              onPress={() => onChange(text)}
              style={({ pressed }) => [
                styles.sceneStarter,
                { borderColor: colors.border, backgroundColor: colors.surface },
                pressed && styles.pressed,
              ]}
            >
              <Text style={[styles.sceneStarterText, { color: colors.text }]}>
                {label}
              </Text>
            </Pressable>
          ))}
        </View>
      </View>
      <TextInput
        testID="assessment-need-input"
        accessibilityLabel="你希望家庭先看清什么"
        multiline
        value={value}
        onChangeText={onChange}
        placeholder="比如：一到写作业就容易争吵，我想知道可以先从哪里开始。"
        placeholderTextColor="#94A3B8"
        style={[
          styles.storyInput,
          {
            color: colors.text,
            borderColor: value ? "#1B7CF2" : colors.border,
            backgroundColor: colors.surface,
          },
        ]}
        textAlignVertical="top"
        maxLength={240}
      />
      <Text style={[styles.inputHint, { color: colors.muted }]}>
        这句话会成为本次测评的起点，后续所有理解都以你确认的内容为准。
      </Text>
      <Pressable
        testID="assessment-voice-sandbox"
        accessibilityRole="button"
        onPress={onVoice}
        style={({ pressed }) => [
          styles.voiceButton,
          { borderColor: colors.border, backgroundColor: colors.surface },
          pressed && styles.pressed,
        ]}
      >
        <Text style={[styles.voiceButtonText, { color: colors.tint }]}>
          {voiceState === "listening"
            ? "正在听…说完即可"
            : "用语音说（当前设备）"}
        </Text>
      </Pressable>
      {voiceState === "unsupported" ? (
        <Text style={styles.voiceHint}>
          当前环境还不能用语音转写，请改用文字。
        </Text>
      ) : (
        <Text style={[styles.voiceHint, { color: colors.muted }]}>
          语音只用于把你的话记下来，结果仍需你确认。
        </Text>
      )}
      <View style={styles.actionStack}>
        <Pressable
          testID="assessment-story-continue"
          accessibilityRole="button"
          onPress={onContinue}
          style={({ pressed }) => [
            styles.primaryButton,
            { backgroundColor: "#1B7CF2" },
            pressed && styles.pressed,
          ]}
        >
          <Text style={styles.primaryButtonText}>继续，开始看见家庭</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          onPress={onContinue}
          style={({ pressed }) => [
            styles.secondaryButton,
            pressed && styles.pressed,
          ]}
        >
          <Text style={[styles.secondaryButtonText, { color: colors.muted }]}>
            先跳过，稍后补充
          </Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          onPress={onSave}
          style={({ pressed }) => [
            styles.saveButton,
            pressed && styles.pressed,
          ]}
        >
          <Text style={[styles.saveButtonText, { color: colors.tint }]}>
            保存并退出
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

function ConsentStep({
  colors,
  projectionState,
  availability,
  remoteCanStart,
  onBack,
  onContinue,
  onExit,
  onRetry,
}: {
  colors: ReturnType<typeof useColors>;
  projectionState: "idle" | "loading" | "ready" | "error";
  availability?: RemoteAssessmentProjection["availability"];
  remoteCanStart: boolean;
  onBack: () => void;
  onContinue: () => void;
  onExit: () => void;
  onRetry: () => void;
}) {
  const blocked =
    availability === "CONSENT_REQUIRED" ||
    availability === "NO_SUBJECT" ||
    availability === "POLICY_BLOCKED";
  return (
    <View style={styles.stepContent}>
      <Text style={[styles.kicker, { color: colors.muted }]}>
        在开始前，先说清楚一次
      </Text>
      <Text style={[styles.title, { color: colors.text }]}>
        这些信息会怎么用？
      </Text>
      <Text style={[styles.subtitle, { color: colors.muted }]}>
        只用来把你这次的家庭关注整理成支持参考。
      </Text>
      <View
        style={[
          styles.explainCard,
          { backgroundColor: colors.surface, borderColor: colors.border },
        ]}
      >
        <ExplainRow text="仅限你的家庭可见，不会公开展示。" />
        <ExplainRow text="只记录你主动说的来意和少量回答。" />
        <ExplainRow text="你可以随时撤回授权、退出或删除这次记录。" />
        <ExplainRow text={ASSESSMENT_BOUNDARY_TEXT} />
      </View>
      {projectionState === "error" ? (
        <View style={styles.inlineError}>
          <Text style={styles.errorText}>暂时无法确认家庭授权，请重试。</Text>
          <Pressable onPress={onRetry}>
            <Text style={styles.retryText}>重新读取</Text>
          </Pressable>
        </View>
      ) : null}
      {blocked ? (
        <View style={styles.blockedCard}>
          <Text style={styles.blockedTitle}>现在还不能开始</Text>
          <Text style={styles.blockedText}>
            {availability === "CONSENT_REQUIRED"
              ? "这个家庭尚未确认测评授权。你可以先保存来意，确认授权后再回来。"
              : "当前家庭暂时没有可用的测评对象或策略。"}
          </Text>
        </View>
      ) : null}
      <View style={styles.actionStack}>
        <Pressable
          testID="assessment-consent-continue"
          accessibilityRole="button"
          disabled={
            !remoteCanStart ||
            projectionState === "loading" ||
            projectionState === "error"
          }
          onPress={onContinue}
          style={({ pressed }) => [
            styles.primaryButton,
            { backgroundColor: remoteCanStart ? "#1B7CF2" : "#CBD5E1" },
            pressed && remoteCanStart && styles.pressed,
          ]}
        >
          <Text style={styles.primaryButtonText}>我明白了，继续</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          onPress={onBack}
          style={({ pressed }) => [
            styles.secondaryButton,
            pressed && styles.pressed,
          ]}
        >
          <Text style={[styles.secondaryButtonText, { color: colors.muted }]}>
            返回修改来意
          </Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          onPress={onExit}
          style={({ pressed }) => [
            styles.saveButton,
            pressed && styles.pressed,
          ]}
        >
          <Text style={[styles.saveButtonText, { color: colors.tint }]}>
            暂时退出，保留草稿
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

function ReflectionStep({
  colors,
  needText,
  selectedFocusId,
  onSelectFocus,
  onBack,
  onCorrect,
  onContinue,
  onSave,
}: {
  colors: ReturnType<typeof useColors>;
  needText: string;
  selectedFocusId: GrowthFocusId | null;
  onSelectFocus: (focusId: GrowthFocusId) => void;
  onBack: () => void;
  onCorrect: () => void;
  onContinue: () => void;
  onSave: () => void;
}) {
  return (
    <View style={styles.stepContent}>
      <View
        style={[
          styles.heardCard,
          { backgroundColor: "#F2F8FF", borderColor: "#D9E8FA" },
        ]}
      >
        <Text style={styles.heardLabel}>我先这样理解</Text>
        <Text style={[styles.heardText, { color: colors.text }]}>
          {needText}
        </Text>
        <Text style={[styles.heardHint, { color: colors.muted }]}>
          这是一份可修改的家庭理解，不会变成对孩子的结论。
        </Text>
      </View>
      <Text style={[styles.title, { color: colors.text }]}>
        这份理解像你们家吗？
      </Text>
      <Text style={[styles.subtitle, { color: colors.muted }]}>
        先确认我有没有听对。接下来会看五个方向，再把你最关心的方向问深一点。
      </Text>
      <View style={styles.dimensionIntroCard}>
        <Text style={styles.dimensionIntroTitle}>五个观察方向</Text>
        <Text style={styles.dimensionIntroText}>
          请选择这次最想先了解的方向。它会得到两道追问，其他四个方向也会各留下一条观察线索。
        </Text>
        <View style={styles.focusList}>
          {UI02_ORIGINAL_FOCUS_LAYOUT.map((focus) => {
            const selected = focus.id === selectedFocusId;
            return (
              <Pressable
                key={focus.id}
                accessibilityRole="button"
                accessibilityState={{ selected }}
                onPress={() => onSelectFocus(focus.id)}
                style={({ pressed }) => [
                  styles.focusCard,
                  selected && styles.focusCardSelected,
                  pressed && styles.pressed,
                ]}
              >
                <View style={styles.focusCopy}>
                  <Text style={styles.focusTitle}>{focus.title}</Text>
                  <Text style={styles.focusSubtitle}>{focus.subtitle}</Text>
                </View>
                <Text style={[styles.focusAction, selected && styles.focusActionSelected]}>
                  {selected ? "先看这个" : "选择"}
                </Text>
              </Pressable>
            );
          })}
        </View>
      </View>
      <View style={styles.actionStack}>
        <Pressable
          testID="assessment-reflection-confirm"
          accessibilityRole="button"
          onPress={onContinue}
          style={({ pressed }) => [
            styles.primaryButton,
            { backgroundColor: "#1B7CF2" },
            pressed && styles.pressed,
          ]}
        >
          <Text style={styles.primaryButtonText}>像我们家，继续深入</Text>
        </Pressable>
        <Pressable
          testID="assessment-reflection-correct"
          accessibilityRole="button"
          onPress={onCorrect}
          style={({ pressed }) => [
            styles.secondaryButton,
            pressed && styles.pressed,
          ]}
        >
          <Text style={[styles.secondaryButtonText, { color: colors.muted }]}>
            不太像，改一下
          </Text>
        </Pressable>
        <Pressable
          testID="assessment-reflection-add"
          accessibilityRole="button"
          onPress={onCorrect}
          style={({ pressed }) => [
            styles.saveButton,
            pressed && styles.pressed,
          ]}
        >
          <Text style={[styles.saveButtonText, { color: colors.tint }]}>
            补充一句
          </Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          onPress={onBack}
          style={({ pressed }) => [
            styles.saveButton,
            pressed && styles.pressed,
          ]}
        >
          <Text style={[styles.saveButtonText, { color: colors.muted }]}>
            返回说明用途
          </Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          onPress={onSave}
          style={({ pressed }) => [
            styles.saveButton,
            pressed && styles.pressed,
          ]}
        >
          <Text style={[styles.saveButtonText, { color: colors.tint }]}>
            保存并退出
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

function QuestionStep({
  colors,
  index,
  total,
  dimensionTitle,
  depth,
  question,
  selectedAnswer,
  onBack,
  onAnswer,
  onSkip,
  onContinue,
  saving,
}: {
  colors: ReturnType<typeof useColors>;
  index: number;
  total: number;
  dimensionTitle: string;
  depth: "OVERVIEW" | "DEEP_DIVE";
  question: string;
  selectedAnswer?: Ui02AssessmentAnswer;
  onBack: () => void;
  onAnswer: (answer: Ui02AssessmentAnswer) => void;
  onSkip: () => void;
  onContinue: () => void;
  saving: boolean;
}) {
  return (
    <View style={styles.stepContent}>
      <Text style={[styles.kicker, { color: colors.muted }]}>
        {depth === "DEEP_DIVE" ? "重点方向 · 深入了解" : "五个方向 · 先看一眼"} · 第 {index + 1} 题 / {total}
      </Text>
      <Text style={styles.questionDimension}>{dimensionTitle}</Text>
      <Text style={[styles.title, { color: colors.text }]}>
        从最近的家庭日常看一眼
      </Text>
      <Text style={[styles.subtitle, { color: colors.muted }]}>
        没有对错。你的回答只帮助我们看见这个方向，选择多少都由你决定。
      </Text>
      <View
        style={[
          styles.questionCard,
          { backgroundColor: colors.surface, borderColor: colors.border },
        ]}
      >
        <Text style={[styles.questionText, { color: colors.text }]}>
          {question}
        </Text>
      </View>
      <View style={styles.answerList}>
        {UI02_ASSESSMENT_ANSWER_OPTIONS.map((option) => {
          const isSelected = selectedAnswer === option.id;
          return (
            <Pressable
              testID={`assessment-answer-${option.id}`}
              key={option.id}
              accessibilityRole="radio"
              accessibilityState={{ selected: isSelected }}
              onPress={() => onAnswer(option.id)}
              style={({ pressed }) => [
                styles.answerButton,
                {
                  backgroundColor: isSelected ? "#EDF4FF" : colors.surface,
                  borderColor: isSelected ? "#1B7CF2" : colors.border,
                },
                pressed && styles.pressed,
              ]}
            >
              <Text
                style={[
                  styles.answerText,
                  { color: isSelected ? "#1B7CF2" : colors.text },
                ]}
              >
                {option.label}
              </Text>
              {isSelected ? (
                <IconSymbol
                  name="checkmark.circle.fill"
                  size={20}
                  color="#1B7CF2"
                />
              ) : null}
            </Pressable>
          );
        })}
      </View>
      <View style={styles.actionStack}>
        <Pressable
          testID="assessment-question-continue"
          accessibilityRole="button"
          disabled={saving}
          onPress={onContinue}
          style={({ pressed }) => [
            styles.primaryButton,
            { backgroundColor: "#1B7CF2" },
            pressed && styles.pressed,
          ]}
        >
          <Text style={styles.primaryButtonText}>
            {saving
              ? "正在保存"
              : index === total - 1
                ? "看见我的整理"
                : "下一件"}
          </Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          onPress={onSkip}
          style={({ pressed }) => [
            styles.secondaryButton,
            pressed && styles.pressed,
          ]}
        >
          <Text style={[styles.secondaryButtonText, { color: colors.muted }]}>
            跳过这一题
          </Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          onPress={onBack}
          style={({ pressed }) => [
            styles.saveButton,
            pressed && styles.pressed,
          ]}
        >
            <Text style={[styles.saveButtonText, { color: colors.tint }]}>
              {index === 0 ? "返回修改理解" : "返回上一题"}
            </Text>
        </Pressable>
      </View>
    </View>
  );
}

function ExplainRow({ text }: { text: string }) {
  return (
    <View style={styles.explainRow}>
      <View style={styles.explainDot} />
      <Text style={styles.explainText}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  content: {
    flexGrow: 1,
    paddingHorizontal: 18,
    paddingTop: 6,
    paddingBottom: 28,
  },
  topBar: {
    height: 48,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  backButton: { width: 42, height: 40, justifyContent: "center" },
  backArrow: { fontSize: 36, lineHeight: 38, fontWeight: "300" },
  screenTitle: {
    position: "absolute",
    left: 42,
    right: 42,
    textAlign: "center",
    fontSize: 17,
    lineHeight: 23,
    fontWeight: "800",
  },
  saveTop: { fontSize: 12, lineHeight: 17 },
  progressBlock: { marginTop: 16, gap: 8 },
  progressLabels: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  progressStep: { fontSize: 13, lineHeight: 18, fontWeight: "900" },
  progressHint: { fontSize: 12, lineHeight: 17 },
  progressTrack: { height: 6, borderRadius: 999, overflow: "hidden" },
  progressValue: { height: "100%", borderRadius: 999 },
  stepContent: { paddingTop: 26, gap: 12 },
  eyebrow: {
    alignSelf: "flex-start",
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  eyebrowText: {
    color: "#1B65C9",
    fontSize: 12,
    lineHeight: 17,
    fontWeight: "900",
  },
  kicker: { fontSize: 13, lineHeight: 18, fontWeight: "800" },
  title: { fontSize: 28, lineHeight: 36, fontWeight: "900", marginTop: 2 },
  subtitle: { fontSize: 14, lineHeight: 22 },
  storyPromise: {
    borderRadius: 16,
    backgroundColor: "#F2F8FF",
    borderWidth: 1,
    borderColor: "#D9E8FA",
    paddingHorizontal: 14,
    paddingVertical: 11,
    gap: 5,
  },
  storyPromiseTitle: {
    color: "#1B65C9",
    fontSize: 12,
    lineHeight: 17,
    fontWeight: "900",
  },
  storyPromiseRow: { flexDirection: "row", alignItems: "center", gap: 7 },
  storyPromiseItem: { color: "#31557D", fontSize: 12, lineHeight: 18 },
  storyPromiseDot: { color: "#8CB4DE", fontSize: 14, lineHeight: 18 },
  sceneStarterBlock: { gap: 8, marginTop: 2 },
  sceneStarterLabel: { fontSize: 12, lineHeight: 17, fontWeight: "800" },
  sceneStarterRow: { flexDirection: "row", gap: 8 },
  sceneStarter: {
    minHeight: 38,
    borderWidth: 1,
    borderRadius: 13,
    paddingHorizontal: 10,
    alignItems: "center",
    justifyContent: "center",
    flex: 1,
  },
  sceneStarterText: { fontSize: 12, lineHeight: 17, fontWeight: "800" },
  storyInput: {
    minHeight: 154,
    borderWidth: 1.2,
    borderRadius: 18,
    padding: 15,
    fontSize: 16,
    lineHeight: 25,
    marginTop: 8,
  },
  inputHint: { fontSize: 12, lineHeight: 18, marginTop: -4 },
  voiceButton: {
    minHeight: 42,
    borderWidth: 1,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  voiceButtonText: { fontSize: 13, lineHeight: 19, fontWeight: "900" },
  voiceHint: {
    color: "#8A5A00",
    fontSize: 11,
    lineHeight: 17,
    textAlign: "center",
    marginTop: -5,
  },
  actionStack: { gap: 8, marginTop: 18 },
  primaryButton: {
    minHeight: 52,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 16,
  },
  primaryButtonText: {
    color: "#FFFFFF",
    fontSize: 16,
    lineHeight: 22,
    fontWeight: "900",
  },
  secondaryButton: {
    minHeight: 42,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 16,
  },
  secondaryButtonText: { fontSize: 13, lineHeight: 20, fontWeight: "800" },
  saveButton: {
    minHeight: 38,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 16,
  },
  saveButtonText: {
    fontSize: 12,
    lineHeight: 18,
    fontWeight: "900",
    textDecorationLine: "underline",
  },
  explainCard: {
    borderWidth: 1,
    borderRadius: 18,
    padding: 15,
    gap: 13,
    marginTop: 8,
  },
  explainRow: { flexDirection: "row", alignItems: "flex-start", gap: 9 },
  explainDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    backgroundColor: "#16866D",
    marginTop: 7,
  },
  explainText: { flex: 1, color: "#334155", fontSize: 14, lineHeight: 21 },
  dimensionIntroCard: {
    borderRadius: 18,
    backgroundColor: "#F7FBFF",
    borderWidth: 1,
    borderColor: "#D7E8FA",
    padding: 14,
    gap: 7,
  },
  dimensionIntroTitle: {
    color: "#173D69",
    fontSize: 15,
    lineHeight: 21,
    fontWeight: "900",
  },
  dimensionIntroText: { color: "#5B7091", fontSize: 12, lineHeight: 18 },
  blockedCard: {
    backgroundColor: "#FFF8E7",
    borderWidth: 1,
    borderColor: "#F4D99B",
    borderRadius: 15,
    padding: 13,
    gap: 4,
  },
  blockedTitle: {
    color: "#8A5A00",
    fontSize: 14,
    lineHeight: 20,
    fontWeight: "900",
  },
  blockedText: { color: "#6F5A36", fontSize: 13, lineHeight: 20 },
  inlineError: {
    backgroundColor: "#FFF1F2",
    borderRadius: 14,
    padding: 12,
    gap: 4,
  },
  retryText: {
    color: "#1B65C9",
    fontSize: 12,
    lineHeight: 18,
    fontWeight: "900",
    textDecorationLine: "underline",
  },
  heardCard: { borderWidth: 1, borderRadius: 18, padding: 15, gap: 6 },
  heardLabel: {
    color: "#1B65C9",
    fontSize: 12,
    lineHeight: 17,
    fontWeight: "900",
  },
  heardText: { fontSize: 17, lineHeight: 25, fontWeight: "800" },
  heardHint: { fontSize: 12, lineHeight: 18 },
  focusList: { gap: 8, marginTop: 4 },
  focusCard: {
    minHeight: 66,
    borderWidth: 1,
    borderRadius: 15,
    paddingHorizontal: 12,
    paddingVertical: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 11,
  },
  focusCardSelected: {
    backgroundColor: "#EEF6FF",
    borderColor: "#75AEF3",
  },
  focusIcon: {
    width: 38,
    height: 38,
    borderRadius: 12,
    alignItems: "center",
    justifyContent: "center",
  },
  focusCopy: { flex: 1, gap: 1 },
  focusTitle: { fontSize: 15, lineHeight: 20, fontWeight: "900" },
  focusSubtitle: { fontSize: 12, lineHeight: 17 },
  focusAction: { color: "#6F8498", fontSize: 11, lineHeight: 16, fontWeight: "900" },
  focusActionSelected: { color: "#1B65C9" },
  questionDimension: { color: "#1B65C9", fontSize: 18, lineHeight: 25, fontWeight: "900" },
  questionCard: {
    borderWidth: 1,
    borderRadius: 18,
    padding: 18,
    minHeight: 126,
    justifyContent: "center",
    marginTop: 8,
  },
  questionText: { fontSize: 20, lineHeight: 29, fontWeight: "900" },
  answerList: { gap: 8, marginTop: 4 },
  answerButton: {
    minHeight: 50,
    borderWidth: 1,
    borderRadius: 15,
    paddingHorizontal: 15,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  answerText: { fontSize: 15, lineHeight: 21, fontWeight: "800" },
  errorText: {
    color: "#B42318",
    fontSize: 12,
    lineHeight: 18,
    textAlign: "center",
    marginTop: 10,
  },
  loadingRow: {
    flexDirection: "row",
    justifyContent: "center",
    alignItems: "center",
    gap: 8,
    marginTop: 18,
  },
  loadingText: { fontSize: 12, lineHeight: 18 },
  pressed: { opacity: 0.78, transform: [{ scale: 0.98 }] },
});
