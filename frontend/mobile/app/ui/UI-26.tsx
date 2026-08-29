import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { COMMUNITY_POST_KIND_OPTIONS, COMMUNITY_TOPICS, PRIVATE_NOTE_TAG_OPTIONS, detectCommunityPrivacyRisks, type CommunityAiTagDraft, type CommunityPostKind } from "@/lib/family/community-content";
import { createMobileRequestId, familyApi } from "@/lib/family/family-api-client";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";
import { trpc } from "@/lib/trpc";

export default function PublishFamilyNoteScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const { communityPostDraft, saveCommunityPostDraft } = useFamilyMobile();
  const [kind, setKind] = useState<CommunityPostKind>(communityPostDraft?.kind ?? "GROWTH_CHECKIN");
  const [title, setTitle] = useState(communityPostDraft?.title ?? "");
  const [body, setBody] = useState(communityPostDraft?.body ?? "");
  const [topic, setTopic] = useState(communityPostDraft?.topic ?? "亲子沟通");
  const [status, setStatus] = useState<"IDLE" | "SAVING" | "SAVED">(communityPostDraft ? "SAVED" : "IDLE");
  const [aiTagDraft, setAiTagDraft] = useState<CommunityAiTagDraft | undefined>(communityPostDraft?.aiTagDraft);
  const tagSuggestion = trpc.privateNoteTags.suggest.useMutation();
  const idempotencyKey = useMemo(() => createMobileRequestId("community-private-draft"), []);
  const privacyRisks = useMemo(() => detectCommunityPrivacyRisks(`${title}\n${body}`), [body, title]);
  const canSave = title.trim().length > 0 && body.trim().length > 0 && privacyRisks.length === 0 && status !== "SAVING";

  const suggestTags = async () => {
    if (!canSave || tagSuggestion.isPending) return;
    const result = await tagSuggestion.mutateAsync({ title, body, topic, privacyAcknowledged: true }).catch(() => null);
    if (!result) return;
    setAiTagDraft({ tags: result.tags, source: result.source, modelGatewayStatus: result.modelGatewayStatus, factBoundary: result.factBoundary });
  };
  const toggleTag = (tag: string) => {
    const previous = aiTagDraft?.tags ?? [];
    const tags = previous.includes(tag) ? previous.filter((item) => item !== tag) : [...previous, tag].slice(0, 5);
    setAiTagDraft({ tags, source: aiTagDraft?.source ?? "MANUAL", modelGatewayStatus: aiTagDraft?.modelGatewayStatus ?? "FALLBACK_RULE_BASED", factBoundary: "TAGS_ARE_EDITABLE_PERSPECTIVE_NOT_FACT" });
  };

  const saveDraft = async () => {
    if (!canSave) return;
    setStatus("SAVING");
    saveCommunityPostDraft(kind, title, body, topic, aiTagDraft);
    if (session.status === "connected" && session.token && session.selectedFamily) {
      await familyApi.recordDevFlowEvent(session.token, session.selectedFamily.family_id, { ui_id: "UI-26", command: "SAVE_COMMUNITY_POST_DRAFT", selection: `${kind}:${topic}` }, idempotencyKey);
    }
    setStatus("SAVED");
  };

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.topBar}><Pressable onPress={() => router.back()} style={styles.topBack}><IconSymbol name="chevron.left" size={26} color="#22272D" /></Pressable><Text style={styles.topTitle}>发布动态</Text><Pressable onPress={() => void saveDraft()} disabled={!canSave}><Text style={[styles.topPublish, { color: canSave ? colors.tint : colors.muted }]}>发布</Text></Pressable></View>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>选择小记类型</Text>
        <View style={styles.kindGrid}>{COMMUNITY_POST_KIND_OPTIONS.map((item) => <Pressable key={item.id} onPress={() => setKind(item.id)} style={({ pressed }) => [styles.kindCard, { backgroundColor: kind === item.id ? `${item.accent}14` : colors.surface, borderColor: kind === item.id ? item.accent : colors.border }, pressed && styles.pressed]}><IconSymbol name={item.id === "GROWTH_CHECKIN" ? "checkmark.circle.fill" : item.id === "MILESTONE" ? "star.fill" : item.id === "HELP_REFLECTION" ? "message.fill" : "book.fill"} size={25} color={item.accent} /><Text style={[styles.kindText, { color: kind === item.id ? item.accent : colors.text }]}>{item.label}</Text></Pressable>)}</View>

        <View style={[styles.inputCard, { backgroundColor: colors.surface, borderColor: colors.border }]}><View style={styles.inputHeader}><Text style={[styles.inputLabel, { color: colors.text }]}>标题</Text><Text style={[styles.counter, { color: colors.muted }]}>{title.length}/30</Text></View><TextInput value={title} onChangeText={(value) => setTitle(value.slice(0, 30))} placeholder="用一句话记下这个时刻" placeholderTextColor={colors.muted} style={[styles.titleInput, { color: colors.text }]} returnKeyType="next" /></View>
        <View style={[styles.bodyCard, { backgroundColor: colors.surface, borderColor: colors.border }]}><View style={styles.inputHeader}><Text style={[styles.inputLabel, { color: colors.text }]}>小记内容</Text><Text style={[styles.counter, { color: colors.muted }]}>{body.length}/800</Text></View><TextInput value={body} onChangeText={(value) => setBody(value.slice(0, 800))} placeholder="写下你的观察、感受或想继续尝试的做法……" placeholderTextColor={colors.muted} style={[styles.bodyInput, { color: colors.text }]} multiline textAlignVertical="top" /></View>

        <View style={[styles.mediaPanel, { backgroundColor: colors.surface, borderColor: colors.border }]}><View style={styles.mediaIcon}><IconSymbol name="photo.fill" size={30} color={colors.muted} /></View><View style={styles.mediaCopy}><Text style={[styles.mediaTitle, { color: colors.text }]}>照片与视频</Text><Text style={[styles.mediaText, { color: colors.muted }]}>当前先保存文字草稿；不会上传媒体或识别孩子。</Text></View></View>

        <Text style={[styles.sectionTitle, { color: colors.text }]}>选择话题</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.topicRow}>{COMMUNITY_TOPICS.map((item) => <Pressable key={item} onPress={() => setTopic(item)} style={({ pressed }) => [styles.topicChip, { backgroundColor: topic === item ? colors.tint : colors.surface, borderColor: topic === item ? colors.tint : colors.border }, pressed && styles.pressed]}><Text style={[styles.topicText, { color: topic === item ? "#FFFFFF" : colors.muted }]}># {item}</Text></Pressable>)}</ScrollView>

        <View style={[styles.aiTagsCard, { backgroundColor: colors.surface, borderColor: colors.border }]}><View style={styles.aiTagsHeader}><View><Text style={[styles.aiTagsTitle, { color: colors.text }]}>小记标签</Text><Text style={[styles.aiTagsText, { color: colors.muted }]}>帮助你以后在家庭空间中检索；生成后仍可删改。</Text></View><Pressable disabled={!canSave || tagSuggestion.isPending} onPress={() => void suggestTags()} style={({ pressed }) => [styles.aiTagButton, { backgroundColor: canSave ? "#EAF2FF" : colors.border }, pressed && canSave && styles.pressed]}><IconSymbol name="star.fill" size={15} color={canSave ? colors.tint : colors.muted} /><Text style={[styles.aiTagButtonText, { color: canSave ? colors.tint : colors.muted }]}>{tagSuggestion.isPending ? "正在整理…" : "帮我提取"}</Text></Pressable></View>{tagSuggestion.isError ? <Text style={[styles.aiTagError, { color: colors.warning }]}>智能整理暂时不可用，你仍可在下方手动选择标签。</Text> : null}{aiTagDraft?.tags.length ? <View style={styles.aiTagChips}>{aiTagDraft.tags.map((item) => <Pressable key={item} onPress={() => toggleTag(item)} style={({ pressed }) => [styles.aiTagChip, pressed && styles.pressed]}><Text style={styles.aiTagChipText}># {item}</Text><Text style={styles.removeMark}>×</Text></Pressable>)}</View> : <Text style={[styles.aiTagEmpty, { color: colors.muted }]}>标签不会替你下结论，只是可编辑的整理建议。</Text>}<View style={styles.manualTags}>{PRIVATE_NOTE_TAG_OPTIONS.filter((item) => !aiTagDraft?.tags.includes(item)).slice(0, 5).map((item) => <Pressable key={item} onPress={() => toggleTag(item)} style={({ pressed }) => [styles.manualTag, { borderColor: colors.border }, pressed && styles.pressed]}><Text style={[styles.manualTagText, { color: colors.muted }]}>+ {item}</Text></Pressable>)}</View>{aiTagDraft ? <Text style={[styles.aiTagSource, { color: colors.muted }]}>{aiTagDraft.source === "MODEL_GATEWAY" ? "由受控智能整理，可按家庭需要调整" : aiTagDraft.source === "MANUAL" ? "由你自己选择，可随时调整" : "当前由本地规则整理，可按家庭需要调整"}</Text> : null}</View>

        <Text style={[styles.sectionTitle, { color: colors.text }]}>可见范围</Text>
        <View style={[styles.visibilityCard, { backgroundColor: colors.surface, borderColor: colors.border }]}><View style={[styles.visibilityIcon, { backgroundColor: "#16866D16" }]}><IconSymbol name="lock.fill" size={23} color={colors.success} /></View><View style={styles.visibilityCopy}><Text style={[styles.visibilityTitle, { color: colors.text }]}>仅家庭可见</Text><Text style={[styles.visibilityText, { color: colors.muted }]}>保存后进入“我的社区”，不会公开发布、通知顾问或同步到挑战。</Text></View><IconSymbol name="eye.fill" size={20} color={colors.success} /></View>

        <Pressable onPress={() => router.push("/ui/UI-09" as Href)} style={({ pressed }) => [styles.taskCard, pressed && styles.pressed]}><View style={styles.taskCheck}><IconSymbol name="checkmark.circle.fill" size={23} color="#FFFFFF" /></View><View style={styles.taskCopy}><Text style={styles.taskLabel}>来自今天的家庭行动</Text><Text style={styles.taskTitle}>完成行动后，可以把观察写成家庭小记</Text></View><IconSymbol name="chevron.right" size={21} color="#F28C45" /></Pressable>

        <View style={[styles.privacyCard, { backgroundColor: privacyRisks.length ? "#FFF3ED" : "#EEF8F4", borderColor: privacyRisks.length ? "#F28C45" : "#16866D" }]}><IconSymbol name="shield.fill" size={21} color={privacyRisks.length ? "#F28C45" : "#16866D"} /><View style={styles.privacyCopy}><Text style={[styles.privacyTitle, { color: colors.text }]}>{privacyRisks.length ? "请先保护家庭隐私" : "保存前的隐私提醒"}</Text><Text style={[styles.privacyText, { color: colors.muted }]}>{privacyRisks.length ? privacyRisks.join("；") : "不要填写孩子姓名、学校、班级、电话、住址或其他可识别信息。"}</Text></View></View>

        {status === "SAVED" ? <View style={[styles.savedCard, { borderColor: colors.success }]}><IconSymbol name="checkmark.circle.fill" size={22} color={colors.success} /><View style={styles.savedCopy}><Text style={[styles.savedTitle, { color: colors.text }]}>小记已保存在家庭空间</Text><Text style={[styles.savedText, { color: colors.muted }]}>这是家长视角的私有草稿，不是事实结论，也没有公开发布。</Text></View></View> : null}
        <Pressable disabled={!canSave} onPress={() => void saveDraft()} style={({ pressed }) => [styles.saveButton, { backgroundColor: canSave ? "#F28C45" : colors.border }, pressed && canSave && styles.pressed]}><IconSymbol name="lock.fill" size={20} color="#FFFFFF" /><Text style={styles.saveText}>{status === "SAVING" ? "正在保存……" : "保存私有小记"}</Text></Pressable>
        <Pressable onPress={() => router.push("/ui/UI-28" as Href)} style={({ pressed }) => [styles.mineButton, { borderColor: colors.tint }, pressed && styles.pressed]}><Text style={[styles.mineText, { color: colors.tint }]}>查看我的社区</Text></Pressable>
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 16, paddingTop: 16, paddingBottom: 42, gap: 13 }, topBar: { minHeight: 40, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, topBack: { width: 38, height: 38, alignItems: "flex-start", justifyContent: "center" }, topTitle: { color: "#22272D", fontSize: 19, lineHeight: 26, fontWeight: "900" }, topPublish: { fontSize: 15, lineHeight: 21, fontWeight: "900" }, sectionTitle: { fontSize: 16, lineHeight: 23, fontWeight: "900" },
  kindGrid: { flexDirection: "row", flexWrap: "wrap", gap: 9 }, kindCard: { width: "48%", minHeight: 82, borderWidth: 1.5, borderRadius: 17, alignItems: "center", justifyContent: "center", gap: 7, paddingHorizontal: 8 }, kindText: { fontSize: 12, lineHeight: 17, fontWeight: "900", textAlign: "center" },
  inputCard: { minHeight: 82, borderWidth: 1, borderRadius: 18, padding: 13, gap: 6 }, bodyCard: { minHeight: 190, borderWidth: 1, borderRadius: 18, padding: 13, gap: 7 }, inputHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" }, inputLabel: { fontSize: 12, lineHeight: 18, fontWeight: "900" }, counter: { fontSize: 9, lineHeight: 13 }, titleInput: { fontSize: 14, lineHeight: 21, paddingVertical: 5 }, bodyInput: { minHeight: 128, fontSize: 13, lineHeight: 21, paddingVertical: 3 },
  mediaPanel: { minHeight: 84, borderWidth: 1, borderRadius: 18, padding: 13, flexDirection: "row", alignItems: "center", gap: 11 }, mediaIcon: { width: 54, height: 54, borderRadius: 16, backgroundColor: "#E9EEF5", alignItems: "center", justifyContent: "center" }, mediaCopy: { flex: 1, gap: 3 }, mediaTitle: { fontSize: 13, lineHeight: 18, fontWeight: "900" }, mediaText: { fontSize: 10, lineHeight: 16 },
  topicRow: { gap: 8 }, topicChip: { minHeight: 36, borderWidth: 1, borderRadius: 18, paddingHorizontal: 14, alignItems: "center", justifyContent: "center" }, topicText: { fontSize: 11, lineHeight: 16, fontWeight: "800" },
  aiTagsCard: { minHeight: 106, borderWidth: 1, borderRadius: 18, padding: 13, gap: 9 }, aiTagsHeader: { flexDirection: "row", justifyContent: "space-between", gap: 10 }, aiTagsTitle: { fontSize: 13, lineHeight: 18, fontWeight: "900" }, aiTagsText: { maxWidth: 195, fontSize: 10, lineHeight: 16 }, aiTagButton: { minHeight: 33, borderRadius: 16, paddingHorizontal: 10, alignItems: "center", justifyContent: "center", flexDirection: "row", gap: 4 }, aiTagButtonText: { fontSize: 10, lineHeight: 14, fontWeight: "900" }, aiTagChips: { flexDirection: "row", flexWrap: "wrap", gap: 7 }, aiTagChip: { flexDirection: "row", alignItems: "center", gap: 3, borderRadius: 13, backgroundColor: "#EAF2FF", paddingHorizontal: 9, paddingVertical: 5 }, aiTagChipText: { color: "#2563EB", fontSize: 10, lineHeight: 14, fontWeight: "800" }, removeMark: { color: "#2563EB", fontSize: 15, lineHeight: 15, fontWeight: "900" }, aiTagEmpty: { fontSize: 10, lineHeight: 16 }, aiTagError: { fontSize: 10, lineHeight: 16, fontWeight: "800" }, manualTags: { flexDirection: "row", flexWrap: "wrap", gap: 6 }, manualTag: { borderWidth: 1, borderRadius: 12, paddingHorizontal: 8, paddingVertical: 4 }, manualTagText: { fontSize: 9, lineHeight: 13, fontWeight: "800" }, aiTagSource: { fontSize: 9, lineHeight: 14 },
  visibilityCard: { minHeight: 84, borderWidth: 1, borderRadius: 19, padding: 13, flexDirection: "row", alignItems: "center", gap: 10 }, visibilityIcon: { width: 45, height: 45, borderRadius: 15, alignItems: "center", justifyContent: "center" }, visibilityCopy: { flex: 1, gap: 3 }, visibilityTitle: { fontSize: 13, lineHeight: 18, fontWeight: "900" }, visibilityText: { fontSize: 10, lineHeight: 16 },
  taskCard: { minHeight: 82, borderRadius: 19, borderWidth: 1, borderColor: "#FFD7BC", backgroundColor: "#FFF6F0", padding: 13, flexDirection: "row", alignItems: "center", gap: 10 }, taskCheck: { width: 39, height: 39, borderRadius: 13, backgroundColor: "#F28C45", alignItems: "center", justifyContent: "center" }, taskCopy: { flex: 1, gap: 2 }, taskLabel: { color: "#B45A22", fontSize: 9, lineHeight: 13, fontWeight: "900" }, taskTitle: { color: "#58311E", fontSize: 12, lineHeight: 18, fontWeight: "800" },
  privacyCard: { minHeight: 82, borderWidth: 1, borderRadius: 18, padding: 13, flexDirection: "row", alignItems: "flex-start", gap: 9 }, privacyCopy: { flex: 1, gap: 3 }, privacyTitle: { fontSize: 12, lineHeight: 17, fontWeight: "900" }, privacyText: { fontSize: 10, lineHeight: 16 }, savedCard: { minHeight: 78, borderWidth: 1, borderRadius: 18, padding: 13, flexDirection: "row", alignItems: "flex-start", gap: 9 }, savedCopy: { flex: 1, gap: 3 }, savedTitle: { fontSize: 12, lineHeight: 17, fontWeight: "900" }, savedText: { fontSize: 10, lineHeight: 16 },
  saveButton: { minHeight: 52, borderRadius: 19, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 7 }, saveText: { color: "#FFFFFF", fontSize: 14, lineHeight: 20, fontWeight: "900" }, mineButton: { minHeight: 48, borderWidth: 1.5, borderRadius: 18, alignItems: "center", justifyContent: "center" }, mineText: { fontSize: 13, lineHeight: 18, fontWeight: "900" }, pressed: { opacity: 0.82, transform: [{ scale: 0.98 }] },
});
