import { router, type Href } from "expo-router";
import { useState } from "react";
import { Modal, ScrollView, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { Fonts } from "@/lib/_core/theme";
import { familyApi, createMobileRequestId } from "@/lib/family/family-api-client";
import type { ExperienceMediaKind, MultimodalDraftResponse } from "@/lib/family/multimodal-api-contracts";

type FlowStep = {
  label: string;
  detail: string;
  icon: "message.fill" | "star.fill" | "checkmark.circle.fill" | "headphones.fill";
};

const FLOW_STEPS: readonly FlowStep[] = [
  { label: "看见需要", detail: "说出此刻最在意的事", icon: "message.fill" },
  { label: "一起理解", detail: "AI 整理视角，家庭来确认", icon: "star.fill" },
  { label: "做一件小事", detail: "今天先走出一小步", icon: "checkmark.circle.fill" },
  { label: "需要时有人", detail: "连接可信的支持与陪伴", icon: "headphones.fill" },
];

function go(path: Href) {
  router.push(path);
}

/**
 * A user-facing family hub that makes the blueprint's value chain visible.
 * It is intentionally separate from the legacy UI-number screens so the
 * product can be reviewed by a family's mental model rather than an
 * implementation identifier.
 */
export function FamilyExperienceHub() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const connected = session.status === "connected";
  const [expressionPickerOpen, setExpressionPickerOpen] = useState(false);
  const [selectedKind, setSelectedKind] = useState<ExperienceMediaKind | null>(null);
  const [expressionText, setExpressionText] = useState("");
  const [draft, setDraft] = useState<MultimodalDraftResponse | null>(null);
  const [draftLoading, setDraftLoading] = useState(false);
  const [draftError, setDraftError] = useState<string | null>(null);

  const mediaOptions: ReadonlyArray<{
    kind: ExperienceMediaKind;
    title: string;
    detail: string;
    icon: "message.fill" | "photo.fill" | "video.fill";
  }> = [
    { kind: "TEXT", title: "写下来", detail: "适合描述经过和想改变的事", icon: "message.fill" },
    { kind: "VOICE", title: "说出来", detail: "不用先把感受整理好", icon: "message.fill" },
    { kind: "IMAGE", title: "拍下来", detail: "记录一个当下的场景", icon: "photo.fill" },
    { kind: "VIDEO", title: "录一小段", detail: "只在你明确授权后使用", icon: "video.fill" },
  ];

  function chooseExpression(kind: ExperienceMediaKind) {
    setSelectedKind(kind);
    if (kind === "TEXT") {
      setDraftError(null);
      if (!session.token || !session.selectedFamily) go("/assessment" as Href);
    }
  }

  async function createTextDraft() {
    const familyId = session.selectedFamily?.family_id;
    if (!session.token || !familyId || !expressionText.trim()) return;
    setDraftLoading(true);
    setDraftError(null);
    try {
      const result = await familyApi.createMultimodalDraft(
        session.token,
        familyId,
        {
          run_id: createMobileRequestId("family-expression"),
          prompt_version: "family-companion.v1",
          schema_version: "family-experience-draft.v1",
          payload: { expression: expressionText.trim() },
          output_schema: {
            type: "object",
            required: ["understanding", "next_step", "path", "limitations"],
          },
          modalities: ["TEXT"],
          estimated_input_tokens: Math.max(64, expressionText.trim().length * 2),
          strategy: "balanced",
        },
        createMobileRequestId("family-expression-draft"),
      );
      setDraft(result);
    } catch (error) {
      setDraftError(error instanceof Error ? error.message : "暂时无法形成理解草案，请稍后再试。");
    } finally {
      setDraftLoading(false);
    }
  }

  async function decideDraft(decision: "confirm" | "reject") {
    const familyId = session.selectedFamily?.family_id;
    if (!session.token || !familyId || !draft) return;
    try {
      await familyApi.decideMultimodalRun(
        session.token,
        familyId,
        draft.run_id,
        { decision, draft_version: draft.provenance.schema_version },
        createMobileRequestId(`family-expression-${decision}`),
      );
      setExpressionPickerOpen(false);
      setDraft(null);
      setExpressionText("");
    } catch (error) {
      setDraftError(error instanceof Error ? error.message : "这次决定暂时没有记录成功。");
    }
  }

  async function deleteDraft() {
    const familyId = session.selectedFamily?.family_id;
    if (!session.token || !familyId || !draft) return;
    try {
      await familyApi.deleteMultimodalRun(session.token, familyId, draft.run_id, "家庭主动删除表达草案", createMobileRequestId("family-expression-delete"));
      setExpressionPickerOpen(false);
      setDraft(null);
      setExpressionText("");
    } catch (error) {
      setDraftError(error instanceof Error ? error.message : "删除请求暂时没有完成。");
    }
  }

  async function requestHumanReview() {
    const familyId = session.selectedFamily?.family_id;
    if (!session.token || !familyId || !draft) return;
    try {
      await familyApi.requestMultimodalHumanReview(
        session.token,
        familyId,
        draft.run_id,
        { reason: "家庭希望人工帮助理解这次表达" },
        createMobileRequestId("family-expression-human-review"),
      );
      setDraftError("已提交人工帮助请求，家庭可以先暂停这次表达。");
    } catch (error) {
      setDraftError(error instanceof Error ? error.message : "人工帮助请求暂时没有提交成功。");
    }
  }

  return (
    <ScreenContainer edges={["top", "left", "right"]} containerClassName="bg-background">
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.header}>
          <View style={styles.headerCopy}>
            <Text style={[styles.eyebrow, { color: colors.primary }]}>WE ARE FAMILY</Text>
            <Text style={[styles.title, { color: colors.text }]}>今天，和家人站在一起</Text>
            <Text style={[styles.subtitle, { color: colors.muted }]}>孩子成长不必独自扛，家庭改变也不用一次做到完美。</Text>
          </View>
          <View style={[styles.heart, { backgroundColor: `${colors.primary}18` }]}>
            <IconSymbol name="heart.fill" size={27} color={colors.primary} />
          </View>
        </View>

        <View style={[styles.trustPill, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <IconSymbol name="shield.fill" size={16} color={colors.primary} />
          <Text style={[styles.trustText, { color: colors.muted }]}>
            {connected ? "家庭上下文已连接" : "本机演示 · 未同步"}
          </Text>
        </View>

        <Pressable
          accessibilityRole="button"
          accessibilityLabel="说说家庭现在最需要什么"
          onPress={() => setExpressionPickerOpen(true)}
          style={({ pressed }) => [styles.hero, { backgroundColor: colors.primary }, pressed && styles.pressed]}
        >
          <View style={styles.heroCopy}>
            <Text style={styles.heroKicker}>从一个真实的小困扰开始</Text>
            <Text style={styles.heroTitle}>说说家庭现在最需要什么</Text>
            <Text style={styles.heroBody}>可以打字、说话或拍下当下的场景，先被听见，再一起决定下一步。</Text>
            <View style={styles.heroAction}>
              <Text style={styles.heroActionText}>选择一种表达方式</Text>
              <IconSymbol name="chevron.right" size={18} color="#FFFFFF" />
            </View>
          </View>
          <View style={styles.heroOrb}>
            <IconSymbol name="message.fill" size={32} color="#FFFFFF" />
          </View>
        </Pressable>

        <View style={styles.sectionHeading}>
          <View>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>我们正在一起完成</Text>
            <Text style={[styles.sectionHint, { color: colors.muted }]}>每一步都由家庭确认，不追求完美分数</Text>
          </View>
          <IconSymbol name="person.2.fill" size={22} color={colors.primary} />
        </View>

        <View style={[styles.goalCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <View style={[styles.goalIcon, { backgroundColor: `${colors.primary}14` }]}>
            <IconSymbol name="heart.fill" size={24} color={colors.primary} />
          </View>
          <View style={styles.goalCopy}>
            <Text style={[styles.goalLabel, { color: colors.muted }]}>家庭本周的小目标</Text>
            <Text style={[styles.goalTitle, { color: colors.text }]}>今晚先完整听孩子说一分钟</Text>
            <Text style={[styles.goalBody, { color: colors.muted }]}>不用急着给答案，先让彼此感到被看见。</Text>
          </View>
          <Pressable accessibilityRole="button" accessibilityLabel="开始今晚的小目标" onPress={() => go("/actions/today" as Href)} style={styles.goalButton}>
            <IconSymbol name="chevron.right" size={20} color={colors.primary} />
          </Pressable>
        </View>

        <View style={[styles.flowCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <View style={styles.flowHeader}>
            <Text style={[styles.flowTitle, { color: colors.text }]}>家庭成长的四个动作</Text>
            <Text style={[styles.flowCaption, { color: colors.primary }]}>一起走</Text>
          </View>
          <View style={styles.flowTrack}>
            {FLOW_STEPS.map((step, index) => (
              <View key={step.label} style={styles.flowStep}>
                <View style={[styles.flowIcon, { backgroundColor: index === 0 ? colors.primary : `${colors.primary}14` }]}>
                  <IconSymbol name={step.icon} size={18} color={index === 0 ? "#FFFFFF" : colors.primary} />
                </View>
                <Text style={[styles.flowLabel, { color: colors.text }]}>{step.label}</Text>
                <Text style={[styles.flowDetail, { color: colors.muted }]}>{step.detail}</Text>
                {index < FLOW_STEPS.length - 1 ? <View style={[styles.flowLine, { backgroundColor: colors.border }]} /> : null}
              </View>
            ))}
          </View>
        </View>

        <Text style={[styles.sectionTitle, { color: colors.text }]}>现在就能做的事</Text>
        <View style={styles.actionGrid}>
          <Pressable accessibilityRole="button" accessibilityLabel="查看今日行动" onPress={() => go("/actions/today" as Href)} style={({ pressed }) => [styles.actionCard, { backgroundColor: `${colors.primary}10`, borderColor: `${colors.primary}35` }, pressed && styles.pressed]}>
            <IconSymbol name="checkmark.circle.fill" size={24} color={colors.primary} />
            <Text style={[styles.actionTitle, { color: colors.text }]}>今日行动</Text>
            <Text style={[styles.actionBody, { color: colors.muted }]}>只做一件小事</Text>
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="找到合适的支持" onPress={() => go("/catalog" as Href)} style={({ pressed }) => [styles.actionCard, { backgroundColor: `${colors.trust}10`, borderColor: `${colors.trust}35` }, pressed && styles.pressed]}>
            <IconSymbol name="headphones.fill" size={24} color={colors.trust} />
            <Text style={[styles.actionTitle, { color: colors.text }]}>找到支持</Text>
            <Text style={[styles.actionBody, { color: colors.muted }]}>需要时有人回应</Text>
          </Pressable>
          <Pressable accessibilityRole="button" accessibilityLabel="查看家庭故事" onPress={() => go("/growth/story" as Href)} style={({ pressed }) => [styles.actionCard, { backgroundColor: `${colors.growth}10`, borderColor: `${colors.growth}35` }, pressed && styles.pressed]}>
            <IconSymbol name="photo.fill" size={24} color={colors.growth} />
            <Text style={[styles.actionTitle, { color: colors.text }]}>保存时刻</Text>
            <Text style={[styles.actionBody, { color: colors.muted }]}>把改变留下来</Text>
          </Pressable>
        </View>

        <Pressable
          accessibilityRole="button"
          accessibilityLabel="选择文字、语音、图片或视频表达"
          onPress={() => setExpressionPickerOpen(true)}
          style={({ pressed }) => [styles.multimodalHint, { backgroundColor: colors.surface, borderColor: colors.border }, pressed && styles.pressed]}
        >
          <View style={styles.multimodalIcons}>
            <IconSymbol name="message.fill" size={18} color={colors.primary} />
            <IconSymbol name="photo.fill" size={18} color={colors.trust} />
            <IconSymbol name="video.fill" size={18} color={colors.growth} />
          </View>
          <View style={styles.multimodalCopy}>
            <Text style={[styles.multimodalTitle, { color: colors.text }]}>不必把感受整理成标准答案</Text>
            <Text style={[styles.multimodalBody, { color: colors.muted }]}>文字、语音、图片和视频，都可以成为家庭被理解的入口。</Text>
          </View>
          <IconSymbol name="chevron.right" size={18} color={colors.muted} />
        </Pressable>
      </ScrollView>

      <Modal animationType="slide" transparent visible={expressionPickerOpen} onRequestClose={() => setExpressionPickerOpen(false)}>
        <View style={styles.modalBackdrop}>
          <Pressable style={styles.modalDismissArea} onPress={() => setExpressionPickerOpen(false)} />
          <View style={[styles.expressionSheet, { backgroundColor: colors.background }]}>
            <View style={styles.sheetHandle} />
            <View style={styles.sheetHeader}>
              <View style={styles.sheetHeaderCopy}>
                <Text style={[styles.sheetTitle, { color: colors.text }]}>你想怎么说？</Text>
                <Text style={[styles.sheetSubtitle, { color: colors.muted }]}>选择一种最自然的方式，之后仍由家人确认。</Text>
              </View>
              <Pressable accessibilityRole="button" accessibilityLabel="关闭表达方式选择" onPress={() => setExpressionPickerOpen(false)} style={styles.closeButton}>
                <Text style={[styles.closeButtonText, { color: colors.muted }]}>×</Text>
              </Pressable>
            </View>
            {!draft ? <View style={styles.expressionGrid}>
              {mediaOptions.map((option) => {
                const selected = selectedKind === option.kind;
                return (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={option.title}
                    key={option.kind}
                    onPress={() => chooseExpression(option.kind)}
                    style={({ pressed }) => [
                      styles.expressionOption,
                      { backgroundColor: colors.surface, borderColor: selected ? colors.primary : colors.border },
                      pressed && styles.pressed,
                    ]}
                  >
                    <View style={[styles.expressionIcon, { backgroundColor: `${colors.primary}${selected ? "22" : "12"}` }]}>
                      <IconSymbol name={option.icon} size={21} color={colors.primary} />
                    </View>
                    <Text style={[styles.expressionTitle, { color: colors.text }]}>{option.title}</Text>
                    <Text style={[styles.expressionDetail, { color: colors.muted }]}>{option.detail}</Text>
                  </Pressable>
                );
              })}
            </View> : null}
            {selectedKind === "TEXT" && !draft ? (
              <View style={[styles.composer, { backgroundColor: colors.surface, borderColor: colors.border }]}>
                <Text style={[styles.composerLabel, { color: colors.text }]}>先说说发生了什么</Text>
                <TextInput
                  accessibilityLabel="家庭表达"
                  multiline
                  onChangeText={setExpressionText}
                  placeholder="例如：每天写作业前，我们很容易开始争吵……"
                  placeholderTextColor={colors.muted}
                  style={[styles.composerInput, { backgroundColor: colors.background, borderColor: colors.border, color: colors.text }]}
                  value={expressionText}
                />
                {draftError ? <Text style={[styles.errorText, { color: "#A85B48" }]}>{draftError}</Text> : null}
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="生成理解草案"
                  disabled={draftLoading || !expressionText.trim() || !session.token || !session.selectedFamily}
                  onPress={() => void createTextDraft()}
                  style={({ pressed }) => [styles.draftButton, { backgroundColor: colors.primary }, (pressed || draftLoading) && styles.pressed]}
                >
                  <Text style={styles.draftButtonText}>{draftLoading ? "正在整理…" : "先看看我们怎样理解"}</Text>
                  <IconSymbol name="chevron.right" size={18} color="#FFFFFF" />
                </Pressable>
              </View>
            ) : null}
            {selectedKind && selectedKind !== "TEXT" && !draft ? (
              <View style={[styles.permissionNote, { backgroundColor: `${colors.trust}12`, borderColor: `${colors.trust}35` }]}>
                <IconSymbol name="shield.fill" size={16} color={colors.trust} />
                <Text style={[styles.permissionText, { color: colors.muted }]}>这类表达需要你明确授权。真实上传、转写或识别尚未在当前环境接通，不会假装已经保存。</Text>
              </View>
            ) : null}
            {draft ? (
              <View style={[styles.draftView, { backgroundColor: colors.surface, borderColor: colors.border }]}>
                <Text style={[styles.draftEyebrow, { color: colors.primary }]}>这是一份可修改的理解草案</Text>
                <Text style={[styles.draftText, { color: colors.text }]}>{readDraftText(draft.output, "understanding")}</Text>
                <View style={[styles.nextStep, { backgroundColor: `${colors.growth}12` }]}>
                  <Text style={[styles.nextStepLabel, { color: colors.text }]}>可以先试的一小步</Text>
                  <Text style={[styles.nextStepText, { color: colors.muted }]}>{readDraftText(draft.output, "next_step")}</Text>
                </View>
                <Text style={[styles.draftBoundary, { color: colors.muted }]}>它不是事实、诊断或对孩子的结论。家庭可以不同意、请求人工或删除。</Text>
                {draftError ? <Text style={[styles.errorText, { color: "#A85B48" }]}>{draftError}</Text> : null}
                <View style={styles.draftActions}>
                  <Pressable accessibilityRole="button" onPress={() => void decideDraft("confirm")} style={[styles.draftButton, { backgroundColor: colors.primary }]}><Text style={styles.draftButtonText}>家庭认可</Text></Pressable>
                  <Pressable accessibilityRole="button" onPress={() => void decideDraft("reject")} style={[styles.outlineButton, { borderColor: colors.border }]}><Text style={[styles.outlineButtonText, { color: colors.text }]}>不同意</Text></Pressable>
                </View>
                <View style={styles.draftSecondaryActions}>
                  <Pressable accessibilityRole="button" onPress={() => void deleteDraft()}><Text style={[styles.linkButton, { color: colors.muted }]}>删除这次表达</Text></Pressable>
                  <Pressable accessibilityRole="button" onPress={() => void requestHumanReview()}><Text style={[styles.linkButton, { color: colors.primary }]}>请求人工帮助</Text></Pressable>
                </View>
              </View>
            ) : null}
            <Text style={[styles.sheetFootnote, { color: colors.muted }]}>家庭内容默认只属于这个家，可以暂停、撤回或删除。</Text>
          </View>
        </View>
      </Modal>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { padding: 22, paddingBottom: 42 },
  header: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 15 },
  headerCopy: { flex: 1, paddingRight: 16 },
  eyebrow: { fontFamily: Fonts.rounded, fontSize: 12, fontWeight: "800", letterSpacing: 1.8, marginBottom: 8 },
  title: { fontFamily: Fonts.rounded, fontSize: 30, fontWeight: "800", lineHeight: 38 },
  subtitle: { fontFamily: Fonts.sans, fontSize: 15, lineHeight: 23, marginTop: 7 },
  heart: { width: 52, height: 52, borderRadius: 26, alignItems: "center", justifyContent: "center" },
  trustPill: { alignSelf: "flex-start", flexDirection: "row", alignItems: "center", gap: 7, borderWidth: 1, borderRadius: 18, paddingHorizontal: 12, paddingVertical: 7, marginBottom: 16 },
  trustText: { fontSize: 12, fontWeight: "700" },
  hero: { borderRadius: 28, padding: 22, minHeight: 205, flexDirection: "row", overflow: "hidden", marginBottom: 27 },
  heroCopy: { flex: 1, paddingRight: 8 },
  heroKicker: { color: "#FFF4E9", fontSize: 12, fontWeight: "800", letterSpacing: 0.4 },
  heroTitle: { color: "#FFFFFF", fontFamily: Fonts.rounded, fontSize: 24, lineHeight: 31, fontWeight: "800", marginTop: 8 },
  heroBody: { color: "#FFF4E9", fontSize: 14, lineHeight: 21, marginTop: 7 },
  heroAction: { flexDirection: "row", alignItems: "center", gap: 5, marginTop: 17 },
  heroActionText: { color: "#FFFFFF", fontSize: 14, fontWeight: "800" },
  heroOrb: { width: 66, height: 66, borderRadius: 33, alignItems: "center", justifyContent: "center", backgroundColor: "#FFFFFF26", marginTop: 12 },
  sectionHeading: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 12 },
  sectionTitle: { fontFamily: Fonts.rounded, fontSize: 20, fontWeight: "800" },
  sectionHint: { fontSize: 12, marginTop: 4 },
  goalCard: { borderWidth: 1, borderRadius: 22, padding: 16, flexDirection: "row", alignItems: "center", marginBottom: 16 },
  goalIcon: { width: 48, height: 48, borderRadius: 16, alignItems: "center", justifyContent: "center", marginRight: 12 },
  goalCopy: { flex: 1 },
  goalLabel: { fontSize: 11, fontWeight: "700" },
  goalTitle: { fontSize: 16, fontWeight: "800", marginTop: 4 },
  goalBody: { fontSize: 12, lineHeight: 18, marginTop: 4 },
  goalButton: { width: 34, height: 34, borderRadius: 17, alignItems: "center", justifyContent: "center", marginLeft: 7 },
  flowCard: { borderWidth: 1, borderRadius: 22, padding: 16, marginBottom: 26 },
  flowHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 16 },
  flowTitle: { fontSize: 15, fontWeight: "800" },
  flowCaption: { fontSize: 12, fontWeight: "800" },
  flowTrack: { flexDirection: "row", justifyContent: "space-between" },
  flowStep: { flex: 1, alignItems: "center", position: "relative" },
  flowIcon: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center", zIndex: 1 },
  flowLabel: { fontSize: 12, fontWeight: "800", marginTop: 8, textAlign: "center" },
  flowDetail: { fontSize: 10, lineHeight: 14, marginTop: 4, textAlign: "center", paddingHorizontal: 2 },
  flowLine: { position: "absolute", top: 17, left: "64%", right: "-36%", height: 1 },
  actionGrid: { flexDirection: "row", gap: 10, marginTop: 12, marginBottom: 18 },
  actionCard: { flex: 1, minHeight: 108, borderRadius: 18, borderWidth: 1, padding: 14 },
  actionTitle: { fontSize: 14, fontWeight: "800", marginTop: 10 },
  actionBody: { fontSize: 11, marginTop: 4 },
  multimodalHint: { flexDirection: "row", alignItems: "center", borderWidth: 1, borderRadius: 18, padding: 14 },
  multimodalIcons: { flexDirection: "row", gap: 8, marginRight: 12 },
  multimodalCopy: { flex: 1 },
  multimodalTitle: { fontSize: 13, fontWeight: "800" },
  multimodalBody: { fontSize: 11, lineHeight: 17, marginTop: 4 },
  modalBackdrop: { flex: 1, justifyContent: "flex-end", backgroundColor: "#18231E55" },
  modalDismissArea: { flex: 1 },
  expressionSheet: { borderTopLeftRadius: 28, borderTopRightRadius: 28, padding: 22, paddingBottom: 34 },
  sheetHandle: { alignSelf: "center", backgroundColor: "#A8B3AB", borderRadius: 3, height: 5, marginBottom: 20, width: 42 },
  sheetHeader: { alignItems: "flex-start", flexDirection: "row", justifyContent: "space-between" },
  sheetHeaderCopy: { flex: 1, paddingRight: 16 },
  sheetTitle: { fontFamily: Fonts.rounded, fontSize: 24, fontWeight: "800" },
  sheetSubtitle: { fontSize: 13, lineHeight: 20, marginTop: 6 },
  closeButton: { alignItems: "center", height: 34, justifyContent: "center", width: 34 },
  closeButtonText: { fontSize: 28, fontWeight: "300", lineHeight: 30 },
  expressionGrid: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginTop: 22 },
  expressionOption: { borderRadius: 18, borderWidth: 1, minHeight: 132, padding: 14, width: "48%" },
  expressionIcon: { alignItems: "center", borderRadius: 14, height: 42, justifyContent: "center", marginBottom: 11, width: 42 },
  expressionTitle: { fontSize: 15, fontWeight: "800" },
  expressionDetail: { fontSize: 11, lineHeight: 16, marginTop: 5 },
  permissionNote: { alignItems: "flex-start", borderRadius: 14, borderWidth: 1, flexDirection: "row", gap: 9, marginTop: 16, padding: 12 },
  permissionText: { flex: 1, fontSize: 11, lineHeight: 17 },
  sheetFootnote: { fontSize: 11, lineHeight: 17, marginTop: 16, textAlign: "center" },
  composer: { borderRadius: 18, borderWidth: 1, marginTop: 18, padding: 14 },
  composerLabel: { fontSize: 14, fontWeight: "800" },
  composerInput: { borderRadius: 12, borderWidth: 1, fontSize: 14, lineHeight: 21, marginTop: 10, minHeight: 112, padding: 12, textAlignVertical: "top" },
  draftButton: { alignItems: "center", borderRadius: 12, flexDirection: "row", justifyContent: "space-between", marginTop: 12, minHeight: 44, paddingHorizontal: 14 },
  draftButtonText: { color: "#FFFFFF", fontSize: 13, fontWeight: "800" },
  errorText: { fontSize: 11, lineHeight: 17, marginTop: 9 },
  draftView: { borderRadius: 18, borderWidth: 1, marginTop: 18, padding: 16 },
  draftEyebrow: { fontSize: 12, fontWeight: "800" },
  draftText: { fontSize: 16, lineHeight: 27, marginTop: 12 },
  nextStep: { borderRadius: 12, marginTop: 16, padding: 13 },
  nextStepLabel: { fontSize: 12, fontWeight: "800" },
  nextStepText: { fontSize: 13, lineHeight: 20, marginTop: 5 },
  draftBoundary: { fontSize: 11, lineHeight: 17, marginTop: 14 },
  draftActions: { flexDirection: "row", gap: 9, marginTop: 16 },
  outlineButton: { alignItems: "center", borderRadius: 12, borderWidth: 1, flex: 1, justifyContent: "center", minHeight: 44, paddingHorizontal: 14 },
  outlineButtonText: { fontSize: 13, fontWeight: "800" },
  draftSecondaryActions: { flexDirection: "row", justifyContent: "space-between", marginTop: 16 },
  linkButton: { fontSize: 11, fontWeight: "700" },
  pressed: { opacity: 0.86, transform: [{ scale: 0.985 }] },
});

function readDraftText(output: Record<string, unknown>, key: "understanding" | "next_step") {
  const value = output[key];
  return typeof value === "string" && value.trim() ? value : "这次暂时没有足够信息形成可核对的草案。";
}
