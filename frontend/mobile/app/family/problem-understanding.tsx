import AsyncStorage from "@react-native-async-storage/async-storage";
import { useLocalSearchParams } from "expo-router";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  ConcernComposer,
  CorrectionConfirmation,
  type AuthorizedMediaAttachment,
  type MultimodalDraftResponse,
  type MultimodalRunInteractionResponse,
  type MultimodalRunReplayResponse,
  type MultimodalInputMode,
  type VoiceCaptureState,
  RecoveryNotice,
  UnderstandingMap,
  answerFollowUpQuestion,
  beginCorrection,
  buildMultimodalDraftRequest,
  buildUnderstandingMap,
  createProblemUnderstandingState,
  isAuthorizedMediaAttachment,
  markUnderstandingFeedbackRecorded,
  markUnderstandingUnavailable,
  receiveUnderstanding,
  retryUnderstanding,
  restoreProblemUnderstandingState,
  resumeSavedProblemUnderstanding,
  saveProblemUnderstandingForLater,
  serializeProblemUnderstandingState,
  selectCurrentDraft,
  skipClarification,
  submitConcern,
  submitCorrection,
  toUnderstandingDraft,
  updateConcernDraft,
  updateCorrectionDraft,
} from "@/features/problem-understanding";
import {
  createMobileRequestId,
  familyApi,
  FamilyApiError,
} from "@/lib/family/family-api-client";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { createPlatformCapabilityRegistry } from "@/lib/platform-capabilities";

const STORAGE_KEY = "aifamily:problem-understanding:generative:v2";
const SANDBOX_IMAGE_ATTACHMENT: AuthorizedMediaAttachment = {
  mediaType: "IMAGE",
  uri: "asset:sandbox/family-homework-transition-v1",
  mimeType: "image/png",
  sha256: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
};
const SANDBOX_ANIMATION_ATTACHMENT: AuthorizedMediaAttachment = {
  mediaType: "IMAGE",
  uri: "asset:sandbox/family-routine-animation-v1",
  mimeType: "image/gif",
  sha256: "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
};
const SANDBOX_VIDEO_ATTACHMENT: AuthorizedMediaAttachment = {
  mediaType: "VIDEO",
  uri: "asset:sandbox/family-evening-transition-video-v1",
  mimeType: "video/mp4",
  sha256: "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
  byteSize: 1_024_000,
};

type SandboxMediaMode = "IMAGE" | "ANIMATION" | "VIDEO";

const SANDBOX_MEDIA: Record<SandboxMediaMode, AuthorizedMediaAttachment> = {
  IMAGE: SANDBOX_IMAGE_ATTACHMENT,
  ANIMATION: SANDBOX_ANIMATION_ATTACHMENT,
  VIDEO: SANDBOX_VIDEO_ATTACHMENT,
};

export default function ProblemUnderstandingRoute() {
  const session = useFamilyApiSession();
  const mediaParams = useLocalSearchParams<{
    media_type?: string;
    media_size_bytes?: string;
    media_uri?: string;
    media_mime_type?: string;
    media_sha256?: string;
  }>();
  const { width } = useWindowDimensions();
  const [state, setState] = useState(createProblemUnderstandingState);
  const [hydrated, setHydrated] = useState(false);
  const [reviewWidth, setReviewWidth] = useState(0);
  const [busyAction, setBusyAction] = useState<
    "human-review" | "delete" | "decision" | null
  >(null);
  const [connectionBusy, setConnectionBusy] = useState(false);
  const [sandboxMediaMode, setSandboxMediaMode] =
    useState<SandboxMediaMode | null>(null);
  const [inputMode, setInputMode] = useState<MultimodalInputMode>("TEXT");
  const [voiceCaptureState, setVoiceCaptureState] =
    useState<VoiceCaptureState>("IDLE");
  const [voiceMessage, setVoiceMessage] = useState<string | null>(null);
  const [operationMessage, setOperationMessage] = useState<string | null>(null);
  const replayCheckedRef = useRef<string | null>(null);
  const map = useMemo(() => buildUnderstandingMap(state), [state]);
  const currentDraft = useMemo(() => selectCurrentDraft(state), [state]);
  const attachments = useMemo<AuthorizedMediaAttachment[]>(() => {
    const attachment: AuthorizedMediaAttachment = {
      mediaType:
        mediaParams.media_type === "VIDEO" ||
        mediaParams.media_mime_type?.startsWith("video/")
          ? "VIDEO"
          : "IMAGE",
      uri: mediaParams.media_uri ?? "",
      mimeType: mediaParams.media_mime_type ?? "",
      sha256: mediaParams.media_sha256 ?? "",
      byteSize: parseMediaByteSize(mediaParams.media_size_bytes),
    };
    if (isAuthorizedMediaAttachment(attachment)) return [attachment];
    return sandboxMediaMode ? [SANDBOX_MEDIA[sandboxMediaMode]] : [];
  }, [
    mediaParams.media_type,
    mediaParams.media_mime_type,
    mediaParams.media_size_bytes,
    mediaParams.media_sha256,
    mediaParams.media_uri,
    sandboxMediaMode,
  ]);
  const hasIncompleteAttachment =
    Boolean(
      mediaParams.media_uri ||
      mediaParams.media_mime_type ||
      mediaParams.media_sha256,
    ) && attachments.length === 0;
  const isCompact = width < 480;
  const isDesktop = width >= 960;
  const isWideReview = reviewWidth >= 760;
  const sessionToken = session.token;
  const selectedFamilyId = session.selectedFamily?.family_id ?? null;
  const mediaCapabilities = useMemo(
    () =>
      createPlatformCapabilityRegistry(
        {
          platform: Platform.OS === "ios" ? "IOS" : "ANDROID",
          environment: process.env.NODE_ENV === "production" ? "PROD" : "DEV",
          locale: "zh-CN",
          tenantScope: session.selectedFamily?.tenant_id,
        },
        { synthetic: process.env.NODE_ENV !== "production" },
      ),
    [session.selectedFamily?.tenant_id],
  );

  useEffect(() => {
    let active = true;
    void AsyncStorage.getItem(STORAGE_KEY)
      .then((saved) => {
        if (active) setState(restoreProblemUnderstandingState(saved));
      })
      .finally(() => {
        if (active) setHydrated(true);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (
      !hydrated ||
      session.status !== "connected" ||
      !sessionToken ||
      !selectedFamilyId ||
      !currentDraft ||
      replayCheckedRef.current === currentDraft.runId
    ) {
      return;
    }
    replayCheckedRef.current = currentDraft.runId;
    void familyApi
      .replayMultimodalUnderstandingRun<MultimodalRunReplayResponse>(
        sessionToken,
        selectedFamilyId,
        currentDraft.runId,
      )
      .then(async (replay) => {
        if (replay.deletion_state !== "deleted") return;
        await AsyncStorage.removeItem(STORAGE_KEY);
        setState(createProblemUnderstandingState());
        setOperationMessage("这次内容已删除，刷新后也不会恢复。");
      })
      .catch((error: unknown) => {
        setOperationMessage(userMessageForError(error, "replay"));
      });
  }, [currentDraft, hydrated, selectedFamilyId, session.status, sessionToken]);

  const requestUnderstanding = async (
    submitted: typeof state,
    text: string,
    revision: number,
  ) => {
    if (
      session.status !== "connected" ||
      !session.token ||
      !session.selectedFamily
    ) {
      setState(markUnderstandingUnavailable(submitted));
      return;
    }
    try {
      const runId = createMobileRequestId(`family-understanding-v${revision}`);
      const response =
        await familyApi.createMultimodalUnderstandingDraft<MultimodalDraftResponse>(
          session.token,
          session.selectedFamily.family_id,
          buildMultimodalDraftRequest({
            runId,
            sessionId: createMobileRequestId("family-understanding-session"),
            expression: text,
            revision,
            attachments,
            conversationTurns: submitted.inputs,
            priorRunId: submitted.drafts.at(-1)?.runId ?? null,
          }),
          `create:${runId}`,
        );
      setState(
        receiveUnderstanding(
          submitted,
          toUnderstandingDraft(
            response,
            session.selectedFamily.tenant_id,
            session.selectedFamily.family_id,
            {
              revision,
              mediaCount: attachments.length,
              sourceRefs: [
                ...submitted.inputs.map((input) => input.inputRef),
                ...attachments.map((attachment) => attachment.uri),
              ],
            },
          ),
        ),
      );
      setOperationMessage(null);
    } catch (error) {
      setState({
        ...markUnderstandingUnavailable(submitted),
        recoveryMessage: userMessageForError(error, "generate"),
      });
    }
  };

  const handleConcernSubmit = () => {
    const text = state.concernDraft.trim();
    const inputRef = createMobileRequestId("guardian-concern");
    const submitted = submitConcern(state, {
      inputRef,
      kind: "CONCERN",
      text,
      createdAt: new Date().toISOString(),
    });
    setState(submitted);
    void requestUnderstanding(submitted, text, 1);
  };

  const handleVoiceCapture = async () => {
    setVoiceCaptureState("CAPTURING");
    setVoiceMessage(null);
    try {
      const consentRef =
        process.env.NODE_ENV === "production"
          ? null
          : "sandbox-consent:family-understanding-voice";
      const permission = await mediaCapabilities
        .get("MEDIA_CAPTURE")
        .requestPermission("VOICE", consentRef);
      if (permission.state !== "AVAILABLE" || !consentRef) {
        setVoiceCaptureState("UNAVAILABLE");
        setVoiceMessage(
          permission.fallback ?? "语音暂时不可用，可以继续用文字表达。",
        );
        return;
      }
      const capture = await mediaCapabilities.get("MEDIA_CAPTURE").capture({
        kind: "VOICE",
        consentRef,
        contentLocale: "zh-CN",
        maxDurationMs: 60_000,
      });
      if (capture.state !== "AVAILABLE" || !capture.value?.synthetic) {
        setVoiceCaptureState("UNAVAILABLE");
        setVoiceMessage(
          capture.fallback ?? "语音没有准备好，可以继续用文字表达。",
        );
        return;
      }
      setState((current) =>
        updateConcernDraft(
          current,
          "最近一到晚上写作业，我们说着说着就会着急。我希望先弄清楚，是任务太难，还是我们催得太紧。",
        ),
      );
      setVoiceCaptureState("READY");
      setVoiceMessage(
        "这是合成语音的沙盒转写，没有上传真实录音。请先修改文字，再决定是否继续。",
      );
    } catch {
      setVoiceCaptureState("UNAVAILABLE");
      setVoiceMessage("语音没有准备好，可以继续用文字表达。");
    }
  };

  const handleAnswerQuestion = (question: string) => {
    setState(answerFollowUpQuestion(state, question));
  };

  const handleReconnect = async () => {
    setConnectionBusy(true);
    setOperationMessage(null);
    try {
      await session.connectDevSession();
      setOperationMessage("已尝试重新连接。连接成功后，可以继续刚才的内容。");
    } catch {
      setOperationMessage("现在还连不上。你的内容没有丢失，请稍后再试。");
    } finally {
      setConnectionBusy(false);
    }
  };

  const handleCorrectionSubmit = async () => {
    const correction = state.correctionDraft.trim();
    const inputKind = state.activeFollowUpQuestion
      ? ("FOLLOW_UP" as const)
      : ("CORRECTION" as const);
    const inputRef = createMobileRequestId(
      inputKind === "FOLLOW_UP" ? "guardian-follow-up" : "guardian-correction",
    );
    const priorDraft = state.drafts.at(-1) ?? null;
    if (
      !priorDraft ||
      session.status !== "connected" ||
      !session.token ||
      !session.selectedFamily
    ) {
      setOperationMessage("暂时无法提交补充。你的内容还在，可以稍后再试。");
      return;
    }
    const submitted = submitCorrection(state, {
      inputRef,
      kind: inputKind,
      text: correction,
      createdAt: new Date().toISOString(),
    });
    setState(submitted);
    try {
      await familyApi.decideMultimodalUnderstandingRun<MultimodalRunInteractionResponse>(
        session.token,
        session.selectedFamily.family_id,
        priorDraft.runId,
        {
          decision: "rewrite",
          draft_version: String(priorDraft.draftVersion),
          replacement_text: correction,
        },
        `rewrite:${priorDraft.runId}:${priorDraft.draftVersion}`,
      );
      await requestUnderstanding(
        submitted,
        [...state.inputs.map((item) => item.text), correction].join(
          "\n\n补充或修正：",
        ),
        priorDraft.draftVersion + 1,
      );
    } catch (error) {
      setState({
        ...markUnderstandingUnavailable(submitted),
        recoveryMessage: userMessageForError(error, "correct"),
      });
    }
  };

  const handleConfirm = async () => {
    if (
      !currentDraft ||
      session.status !== "connected" ||
      !session.token ||
      !session.selectedFamily
    ) {
      setOperationMessage("暂时无法记下反馈。你的内容还在，可以稍后再试。");
      return;
    }
    setBusyAction("decision");
    try {
      await familyApi.decideMultimodalUnderstandingRun<MultimodalRunInteractionResponse>(
        session.token,
        session.selectedFamily.family_id,
        currentDraft.runId,
        {
          decision: "confirm",
          draft_version: String(currentDraft.draftVersion),
        },
        `confirm:${currentDraft.runId}:${currentDraft.draftVersion}`,
      );
      setState(markUnderstandingFeedbackRecorded(state));
      setOperationMessage("已记下：这份理解比较贴近你的情况。");
    } catch (error) {
      setOperationMessage(userMessageForError(error, "decision"));
    } finally {
      setBusyAction(null);
    }
  };

  const handleHumanReview = async () => {
    if (
      !currentDraft ||
      session.status !== "connected" ||
      !session.token ||
      !session.selectedFamily
    ) {
      setOperationMessage("暂时无法联系人工作者。你的内容还在，可以稍后再试。");
      return;
    }
    setBusyAction("human-review");
    try {
      await familyApi.requestMultimodalHumanReview<MultimodalRunInteractionResponse>(
        session.token,
        session.selectedFamily.family_id,
        currentDraft.runId,
        { reason: "家长希望人工核对这份理解。" },
        `human-review:${currentDraft.runId}`,
      );
      setOperationMessage("已收到，我们会请人工帮你核对这份理解。");
    } catch (error) {
      setOperationMessage(userMessageForError(error, "human-review"));
    } finally {
      setBusyAction(null);
    }
  };

  const handleSaveAndExit = async () => {
    const saved = saveProblemUnderstandingForLater(
      state,
      new Date().toISOString(),
    );
    await AsyncStorage.setItem(
      STORAGE_KEY,
      serializeProblemUnderstandingState(saved),
    );
    setState(saved);
  };

  const handleDelete = async () => {
    if (
      !currentDraft ||
      session.status !== "connected" ||
      !session.token ||
      !session.selectedFamily
    ) {
      setOperationMessage("暂时无法删除。内容仍然保留，你可以稍后重试。");
      return;
    }
    setBusyAction("delete");
    try {
      await familyApi.deleteMultimodalUnderstandingRun<MultimodalRunInteractionResponse>(
        session.token,
        session.selectedFamily.family_id,
        currentDraft.runId,
        { reason: "家长删除本次家庭理解草案。" },
        `delete:${currentDraft.runId}`,
      );
      await AsyncStorage.removeItem(STORAGE_KEY);
      replayCheckedRef.current = currentDraft.runId;
      setState(createProblemUnderstandingState());
      setOperationMessage("这次内容已删除，刷新后也不会恢复。");
    } catch (error) {
      if (error instanceof FamilyApiError && error.status === 410) {
        await AsyncStorage.removeItem(STORAGE_KEY);
        setState(createProblemUnderstandingState());
        setOperationMessage("这次内容已经删除，不会再次恢复。");
      } else {
        setOperationMessage(userMessageForError(error, "delete"));
      }
    } finally {
      setBusyAction(null);
    }
  };

  const handleStartNew = async () => {
    await AsyncStorage.removeItem(STORAGE_KEY);
    setState(createProblemUnderstandingState());
  };

  if (!hydrated) {
    return (
      <SafeAreaView style={styles.safeArea}>
        <View accessibilityRole="progressbar" style={styles.loadingCard}>
          <Text style={styles.confirmedTitle}>正在找回你上次保存的内容…</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (state.phase === "SAVED") {
    return (
      <SafeAreaView style={styles.safeArea}>
        <View style={styles.savedScreen}>
          <View style={styles.confirmedCard}>
            <Text accessibilityRole="header" style={styles.confirmedTitle}>
              已为你保存
            </Text>
            <Text style={styles.confirmedBody}>
              下次打开会回到这份理解。你也可以现在继续，或删除已保存内容。
            </Text>
          </View>
          {operationMessage ? (
            <View accessibilityRole="alert" style={styles.operationNotice}>
              <Text style={styles.confirmedBody}>{operationMessage}</Text>
            </View>
          ) : null}
          <Pressable
            accessibilityRole="button"
            onPress={() => setState(resumeSavedProblemUnderstanding(state))}
            style={styles.primaryButton}
          >
            <Text style={styles.primaryButtonText}>继续这次对话</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            disabled={busyAction !== null}
            onPress={handleDelete}
            style={[
              styles.secondaryButton,
              busyAction !== null && styles.disabledButton,
            ]}
          >
            <Text style={styles.secondaryButtonText}>
              {busyAction === "delete" ? "正在删除" : "删除已保存内容"}
            </Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView
        contentContainerStyle={[
          styles.content,
          isCompact && styles.contentCompact,
          isDesktop && styles.contentWide,
        ]}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
        style={styles.scroll}
      >
        <View style={styles.hero}>
          <View style={styles.previewPill}>
            <Text style={styles.previewText}>家庭对话体验</Text>
          </View>
          <Text accessibilityRole="header" style={styles.heroTitle}>
            今天，想先把哪件事说清楚？
          </Text>
          <Text style={styles.heroBody}>
            说一件正在困扰你的事。你会先看到我们的理解，修正后再由你确认。
          </Text>
          <View
            accessibilityLabel="说出困扰，确认理解，继续深入理解"
            style={styles.steps}
          >
            <Text style={styles.stepActive}>1 说出困扰</Text>
            <Text style={styles.stepArrow}>→</Text>
            <Text style={styles.step}>2 确认理解</Text>
            <Text style={styles.stepArrow}>→</Text>
            <Text style={styles.step}>3 继续深入理解</Text>
          </View>
        </View>

        {attachments.length > 0 ? (
          <View accessibilityRole="summary" style={styles.attachmentNotice}>
            <Text style={styles.attachmentTitle}>
              {sandboxMediaMode
                ? `已附加 1 个测试${attachmentLabel(attachments[0])}`
                : `已附加 1 个${attachmentLabel(attachments[0])}`}
            </Text>
            <Text style={styles.confirmedBody}>
              {sandboxMediaMode
                ? "仅用于本地沙盒验证，不代表任何真实家庭资料。"
                : "只会把已授权的媒体引用交给家庭理解服务，不会由这个页面自行读取相册或视频库。"}
            </Text>
            {sandboxMediaMode ? (
              <Pressable
                accessibilityRole="button"
                onPress={() => setSandboxMediaMode(null)}
                style={styles.secondaryButton}
              >
                <Text style={styles.secondaryButtonText}>移除测试媒体</Text>
              </Pressable>
            ) : null}
          </View>
        ) : null}

        {hasIncompleteAttachment ? (
          <View accessibilityRole="alert" style={styles.warningNotice}>
            <Text style={styles.attachmentTitle}>这张图片还不能使用</Text>
            <Text style={styles.confirmedBody}>
              请从家庭媒体库重新选择。文字内容仍可继续提交。
            </Text>
          </View>
        ) : null}

        {session.status !== "connected" ? (
          <View accessibilityRole="alert" style={styles.warningNotice}>
            <Text style={styles.attachmentTitle}>家庭服务暂时没有连接</Text>
            <Text style={styles.confirmedBody}>
              你写下的内容不会丢失。重新连接后可以继续整理。
            </Text>
            {session.configured ? (
              <Pressable
                accessibilityRole="button"
                disabled={connectionBusy || session.status === "loading"}
                onPress={handleReconnect}
                style={[
                  styles.secondaryButton,
                  (connectionBusy || session.status === "loading") &&
                    styles.disabledButton,
                ]}
              >
                <Text style={styles.secondaryButtonText}>
                  {connectionBusy || session.status === "loading"
                    ? "正在重新连接"
                    : "重新连接"}
                </Text>
              </Pressable>
            ) : null}
          </View>
        ) : null}

        {operationMessage ? (
          <View accessibilityRole="alert" style={styles.operationNotice}>
            <Text style={styles.confirmedBody}>{operationMessage}</Text>
          </View>
        ) : null}

        {state.inputs.length === 0 ? (
          <ConcernComposer
            attachedMediaMimeType={attachments[0]?.mimeType ?? null}
            canRemoveImage={sandboxMediaMode !== null}
            canUseSandboxImage={
              process.env.NODE_ENV !== "production" && attachments.length === 0
            }
            imageAttached={attachments.length > 0}
            inputMode={inputMode}
            onChangeText={(value) => setState(updateConcernDraft(state, value))}
            onChangeInputMode={(mode) => {
              setInputMode(mode);
              if (
                mode !== "IMAGE" &&
                mode !== "ANIMATION" &&
                mode !== "VIDEO"
              ) {
                return;
              }
              if (sandboxMediaMode && sandboxMediaMode !== mode) {
                setSandboxMediaMode(null);
              }
            }}
            onSubmit={handleConcernSubmit}
            onToggleSandboxImage={() => {
              if (
                inputMode !== "IMAGE" &&
                inputMode !== "ANIMATION" &&
                inputMode !== "VIDEO"
              ) {
                return;
              }
              setSandboxMediaMode((selected) =>
                selected === inputMode ? null : inputMode,
              );
            }}
            onVoiceCapture={() => void handleVoiceCapture()}
            phase={state.phase}
            value={state.concernDraft}
            voiceCaptureState={voiceCaptureState}
            voiceMessage={voiceMessage}
          />
        ) : null}

        {state.phase === "UNDERSTANDING" && !map ? (
          <View accessibilityRole="progressbar" style={styles.loadingCard}>
            <Text style={styles.confirmedTitle}>正在整理这件事…</Text>
            <Text style={styles.confirmedBody}>
              我们会把听到的重点、还不确定的地方和依据分开呈现。
            </Text>
          </View>
        ) : null}

        {map ? (
          <View
            onLayout={(event) => setReviewWidth(event.nativeEvent.layout.width)}
            style={[
              styles.reviewLayout,
              isWideReview && styles.reviewLayoutWide,
            ]}
          >
            <View style={styles.reviewMain}>
              <UnderstandingMap
                model={map}
                onAnswerQuestion={handleAnswerQuestion}
              />
            </View>
            {state.phase !== "CONFIRMED" ? (
              <View
                style={[
                  styles.reviewRail,
                  isWideReview && styles.reviewRailWide,
                ]}
              >
                <CorrectionConfirmation
                  canConfirm={map.canConfirm}
                  canCorrect={map.canCorrect}
                  correction={state.correctionDraft}
                  followUpQuestion={state.activeFollowUpQuestion}
                  onBeginCorrection={() => setState(beginCorrection(state))}
                  onChangeCorrection={(value) =>
                    setState(updateCorrectionDraft(state, value))
                  }
                  onConfirm={handleConfirm}
                  onDelete={handleDelete}
                  onRequestHumanReview={handleHumanReview}
                  onSaveAndExit={handleSaveAndExit}
                  onSkipClarification={() => setState(skipClarification(state))}
                  onSubmitCorrection={handleCorrectionSubmit}
                  phase={state.phase}
                  busyAction={busyAction}
                />
              </View>
            ) : null}
          </View>
        ) : null}

        {(state.phase === "AI_UNAVAILABLE" || state.phase === "ERROR") &&
        state.recoveryMessage ? (
          <RecoveryNotice
            message={state.recoveryMessage}
            onRetry={() => {
              const retrying = retryUnderstanding(state);
              const lastInput = retrying.inputs.at(-1);
              const priorDraft = retrying.drafts.at(-1) ?? null;
              setState(retrying);
              if (!lastInput) {
                setState(markUnderstandingUnavailable(retrying));
                return;
              }
              void requestUnderstanding(
                retrying,
                retrying.inputs
                  .map((item) => item.text)
                  .join("\n\n补充或修正："),
                priorDraft ? priorDraft.draftVersion + 1 : 1,
              );
            }}
          />
        ) : null}

        {state.phase === "CONFIRMED" ? (
          <View style={styles.confirmedLayout}>
            <View style={styles.confirmedCard}>
              <Text accessibilityRole="header" style={styles.confirmedTitle}>
                已记下你的反馈
              </Text>
              <Text style={styles.confirmedBody}>
                这表示当前草案比较贴近你的情况，不会自动改变家庭记录。
              </Text>
              <Pressable
                accessibilityRole="button"
                onPress={handleStartNew}
                style={styles.secondaryButton}
              >
                <Text style={styles.secondaryButtonText}>补充新情况</Text>
              </Pressable>
              <Text style={styles.confirmedBody}>
                也可以开始一次新的理解；之前的草案仍由后端按你的删除选择处理。
              </Text>
              <Pressable
                accessibilityRole="button"
                onPress={handleStartNew}
                style={styles.primaryButton}
              >
                <Text style={styles.primaryButtonText}>开始新的理解</Text>
              </Pressable>
            </View>
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

function userMessageForError(
  error: unknown,
  action:
    | "generate"
    | "correct"
    | "decision"
    | "human-review"
    | "delete"
    | "replay",
): string {
  if (!(error instanceof FamilyApiError)) {
    return "连接暂时不可用。你的内容还在，可以稍后重试。";
  }
  if (error.status === 401)
    return "登录状态已失效。请重新登录，你写下的内容仍然保留。";
  if (error.status === 403)
    return "当前家庭暂时不能完成这一步。你的内容不会丢失。";
  if (error.status === 409)
    return "内容刚刚发生了变化，请重新打开最新版本后再试。";
  if (error.status === 410) return "这次内容已经删除，不会再次恢复。";
  if (action === "delete") return "删除没有完成，内容仍然保留。请稍后再试。";
  if (action === "human-review")
    return "暂时无法联系人工作者。你的内容还在，可以稍后再试。";
  if (action === "replay")
    return "暂时无法核对上次状态。已保存内容仍保留在本机。";
  return "这次理解暂时没有完成。你说过的内容已经保留，可以稍后继续。";
}

function attachmentLabel(
  attachment: AuthorizedMediaAttachment | undefined,
): string {
  if (!attachment) return "媒体";
  if (attachment.mediaType === "VIDEO") return "视频";
  if (
    attachment.mimeType === "image/gif" ||
    attachment.mimeType === "image/webp"
  ) {
    return "动图";
  }
  return "图片";
}

function parseMediaByteSize(value: string | undefined): number | undefined {
  if (value === undefined || !/^\d+$/.test(value)) return undefined;
  const size = Number(value);
  return Number.isSafeInteger(size) ? size : undefined;
}

const styles = StyleSheet.create({
  attachmentNotice: {
    backgroundColor: "#EEF4E9",
    borderColor: "#C8D8BE",
    borderRadius: 18,
    borderWidth: 1,
    gap: 5,
    maxWidth: 720,
    padding: 16,
  },
  attachmentTitle: { color: "#30462A", fontSize: 16, fontWeight: "700" },
  confirmedBody: {
    color: "#5F5147",
    fontSize: 16,
    lineHeight: 25,
  },
  confirmedCard: {
    backgroundColor: "#EEF4E9",
    borderColor: "#C8D8BE",
    borderRadius: 22,
    borderWidth: 1,
    gap: 10,
    padding: 20,
  },
  confirmedLayout: { gap: 14, maxWidth: 720 },
  confirmedTitle: {
    color: "#30462A",
    fontSize: 22,
    fontWeight: "800",
    lineHeight: 30,
  },
  disabledButton: { opacity: 0.45 },
  content: {
    alignSelf: "center",
    gap: 16,
    maxWidth: 1180,
    paddingBottom: 48,
    paddingHorizontal: 32,
    paddingTop: 28,
    width: "100%",
  },
  contentCompact: { paddingHorizontal: 16, paddingTop: 16 },
  contentWide: { gap: 24, paddingBottom: 72, paddingTop: 44 },
  hero: { gap: 12, maxWidth: 760 },
  heroBody: {
    color: "#64584F",
    fontSize: 16,
    lineHeight: 25,
    maxWidth: 650,
  },
  heroTitle: {
    color: "#2D261F",
    fontSize: 30,
    fontWeight: "800",
    lineHeight: 39,
  },
  loadingCard: { margin: 24, padding: 20 },
  operationNotice: {
    backgroundColor: "#F5F1EC",
    borderRadius: 16,
    maxWidth: 720,
    padding: 14,
  },
  primaryButton: {
    alignItems: "center",
    backgroundColor: "#D8663A",
    borderRadius: 16,
    padding: 15,
  },
  primaryButtonText: { color: "#FFFFFF", fontSize: 16, fontWeight: "700" },
  previewPill: {
    alignSelf: "flex-start",
    backgroundColor: "#F3E8DF",
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  previewText: {
    color: "#775747",
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 0.4,
  },
  reviewLayout: { gap: 18 },
  reviewLayoutWide: {
    alignItems: "flex-start",
    flexDirection: "row",
    gap: 28,
  },
  reviewMain: { flex: 1, minWidth: 0 },
  reviewRail: { width: "100%" },
  reviewRailWide: { flexShrink: 0, width: 340 },
  safeArea: { backgroundColor: "#FFF9F5", flex: 1 },
  scroll: { backgroundColor: "#FFF9F5", flex: 1 },
  savedScreen: {
    alignSelf: "center",
    gap: 12,
    maxWidth: 680,
    padding: 20,
    width: "100%",
  },
  secondaryButton: {
    alignItems: "center",
    backgroundColor: "#F8EEE7",
    borderColor: "#DFA889",
    borderRadius: 16,
    borderWidth: 1,
    padding: 15,
  },
  secondaryButtonText: { color: "#7C3D27", fontSize: 16, fontWeight: "700" },
  step: { color: "#786B61", fontSize: 13, fontWeight: "700" },
  stepActive: { color: "#A74624", fontSize: 13, fontWeight: "800" },
  stepArrow: { color: "#BFA99A", fontSize: 13 },
  steps: {
    alignItems: "center",
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 7,
  },
  warningNotice: {
    backgroundColor: "#FFF4EC",
    borderColor: "#EBC3A9",
    borderRadius: 18,
    borderWidth: 1,
    gap: 5,
    maxWidth: 720,
    padding: 16,
  },
});
