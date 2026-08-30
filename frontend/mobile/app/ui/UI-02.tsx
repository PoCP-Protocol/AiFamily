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
  getUi02DeepAssessmentQuestions,
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

const FOCUS_ICON: Record<
  string,
  {
    name:
      | "book.fill"
      | "heart.fill"
      | "message.fill"
      | "phone.fill"
      | "shield.fill";
    color: string;
  }
> = {
  LEARNING_HABITS: { name: "book.fill", color: "#2F9BE0" },
  EMOTION_REGULATION: { name: "message.fill", color: "#F5943A" },
  PARENT_CHILD_COMMUNICATION: { name: "heart.fill", color: "#F0555C" },
  DEVICE_USE_CONTEXT: { name: "phone.fill", color: "#5B7CF0" },
  SELF_REGULATION: { name: "shield.fill", color: "#3FB667" },
};

const ASSESSMENT_BOUNDARY_TEXT = "这是家庭自查，不给孩子打分，不做诊断或排名。";
const STEP_LABELS: Record<FlowStep, string> = {
  story: "说说来意",
  consent: "说明用途",
  focus: "选一小块",
  questions: "回答三题",
};

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
  const selectedQuestions = getUi02DeepAssessmentQuestions(selectedFocusId);
  const currentQuestion = selectedQuestions[questionIndex];
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
    ? `我听到你想先把“${displayNeed.length > 46 ? `${displayNeed.slice(0, 46)}…` : displayNeed}”这件小事理清，不急着给孩子下结论。`
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
    if (flowStep === "questions" && selectedQuestions.length === 0)
      setAssessmentStep("focus");
    if (
      questionIndex >= selectedQuestions.length &&
      selectedQuestions.length > 0
    )
      setQuestionIndex(0);
  }, [flowStep, questionIndex, selectedQuestions.length, setAssessmentStep]);

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
        for (const question of selectedQuestions) {
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
    router.push("/ui/UI-02-result" as Href);
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
    setAssessmentStep("focus");
  };

  const continueQuestion = () => {
    if (!currentQuestion) return;
    if (!currentAnswer) {
      setSubmissionError("可以选择一个答案，也可以按“跳过这一题”。");
      return;
    }
    setSubmissionError(null);
    if (questionIndex < selectedQuestions.length - 1)
      setQuestionIndex((value) => value + 1);
    else void saveFocus();
  };

  const skipQuestion = () => {
    setSubmissionError(null);
    if (questionIndex < selectedQuestions.length - 1)
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
            家庭小事整理
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
          <FocusStep
            colors={colors}
            needText={reflectedNeed}
            selected={selectedFocusId}
            onBack={() => setAssessmentStep("consent")}
            onSelect={(focus) => {
              selectGrowthFocus(focus);
              setQuestionIndex(0);
            }}
            onContinue={() => {
              setAssessmentStep("questions");
              setQuestionIndex(0);
            }}
            onSave={leaveWithDraft}
          />
        ) : null}
        {flowStep === "questions" && currentQuestion ? (
          <QuestionStep
            colors={colors}
            index={questionIndex}
            total={selectedQuestions.length}
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
        <Text style={styles.eyebrowText}>从一件家庭小事开始</Text>
      </View>
      <Text style={[styles.title, { color: colors.text }]}>
        你现在最想解决什么？
      </Text>
      <Text style={[styles.subtitle, { color: colors.muted }]}>
        先用你自己的话说。不用选标签，也不用把事情讲完整。
      </Text>
      <TextInput
        testID="assessment-need-input"
        accessibilityLabel="你现在最想解决什么"
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
        这句话只用于这次家庭自查的理解和回看。
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
            : "🎙 用语音说（sandbox）"}
        </Text>
      </Pressable>
      {voiceState === "unsupported" ? (
        <Text style={styles.voiceHint}>
          当前环境未启用语音转写，请改用文字；sandbox 语音不会发送给模型。
        </Text>
      ) : (
        <Text style={[styles.voiceHint, { color: colors.muted }]}>
          语音转写只在当前设备完成，sandbox 结果仍需你确认。
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
          <Text style={styles.primaryButtonText}>继续，把这件事理清</Text>
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

function FocusStep({
  colors,
  needText,
  selected,
  onBack,
  onSelect,
  onContinue,
  onSave,
}: {
  colors: ReturnType<typeof useColors>;
  needText: string;
  selected: GrowthFocusId | null;
  onBack: () => void;
  onSelect: (focus: GrowthFocusId) => void;
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
          如果不准确，可以返回修改。
        </Text>
      </View>
      <Text style={[styles.title, { color: colors.text }]}>
        哪一小块最相关？
      </Text>
      <Text style={[styles.subtitle, { color: colors.muted }]}>
        选一个就好。它只是帮我们决定接下来问哪三件小事。
      </Text>
      <View style={styles.focusList}>
        {UI02_ORIGINAL_FOCUS_LAYOUT.map((item) => {
          const isSelected = item.id === selected;
          const icon =
            FOCUS_ICON[item.id] ?? FOCUS_ICON.PARENT_CHILD_COMMUNICATION;
          return (
            <Pressable
              testID={`assessment-focus-${item.id}`}
              key={item.id}
              accessibilityRole="radio"
              accessibilityState={{ selected: isSelected }}
              onPress={() => {
                onSelect(item.id);
                haptic.selection();
              }}
              style={({ pressed }) => [
                styles.focusCard,
                {
                  backgroundColor: isSelected ? "#EDF4FF" : colors.surface,
                  borderColor: isSelected ? "#1B7CF2" : colors.border,
                },
                pressed && styles.pressed,
              ]}
            >
              <View style={[styles.focusIcon, { backgroundColor: icon.color }]}>
                <IconSymbol name={icon.name} size={19} color="#FFFFFF" />
              </View>
              <View style={styles.focusCopy}>
                <Text style={[styles.focusTitle, { color: colors.text }]}>
                  {item.title}
                </Text>
                <Text style={[styles.focusSubtitle, { color: colors.muted }]}>
                  {item.subtitle}
                </Text>
              </View>
              {isSelected ? (
                <IconSymbol
                  name="checkmark.circle.fill"
                  size={22}
                  color="#1B7CF2"
                />
              ) : null}
            </Pressable>
          );
        })}
      </View>
      <View style={styles.actionStack}>
        <Pressable
          testID="assessment-focus-continue"
          accessibilityRole="button"
          disabled={!selected}
          onPress={onContinue}
          style={({ pressed }) => [
            styles.primaryButton,
            { backgroundColor: selected ? "#1B7CF2" : "#CBD5E1" },
            pressed && selected && styles.pressed,
          ]}
        >
          <Text style={styles.primaryButtonText}>继续回答三题</Text>
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
        只问三件小事 · 第 {index + 1} 题 / {total}
      </Text>
      <Text style={[styles.title, { color: colors.text }]}>
        最近的家庭日常里，哪种情况更接近？
      </Text>
      <Text style={[styles.subtitle, { color: colors.muted }]}>
        没有对错。你的选择只帮助我们找到今天可以试的一小步。
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
            {index === 0 ? "返回选择方向" : "返回上一题"}
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
