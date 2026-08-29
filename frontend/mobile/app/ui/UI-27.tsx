import type { Href } from "expo-router";
import { Stack, router, useLocalSearchParams } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { FamilyRefreshControl } from "@/components/family/family-refresh-control";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { familyApi } from "@/lib/family/family-api-client";
import { selectLearningExchangeEntry, selectLearningExchangeFeed, type FamilyApiPlatformSurfacesProjection } from "@/lib/family/family-api-projections";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";

export default function FamilyNoteDetailScreen() {
  const colors = useColors();
  const params = useLocalSearchParams<{ exchangeRef?: string }>();
  const session = useFamilyApiSession();
  const { communityInteractionDrafts, toggleCommunityBookmark, toggleCommunityFollow, saveCommunityResponseDraft } = useFamilyMobile();
  const [projection, setProjection] = useState<FamilyApiPlatformSurfacesProjection | null>(null);
  const [responseText, setResponseText] = useState("");
  const [saved, setSaved] = useState(false);
  const [relatedVisible, setRelatedVisible] = useState(2);

  useEffect(() => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) return;
    let active = true;
    familyApi.getDevPlatformSurfaces<FamilyApiPlatformSurfacesProjection>(session.token, session.selectedFamily.family_id)
      .then((result) => { if (active) setProjection(result); })
      .catch((error) => { console.error("UI-27 remote projection failed", error); });
    return () => { active = false; };
  }, [session.selectedFamily, session.status, session.token]);

  const entry = selectLearningExchangeEntry(projection, params.exchangeRef);
  const exchangeRef = entry?.exchange_ref ?? params.exchangeRef ?? "EXCHANGE_DIALOGUE_PAUSE";
  const interaction = communityInteractionDrafts[exchangeRef];
  const title = entry?.title ?? "给一次对话留一点停顿";
  const summary = entry?.summary ?? "有家长会在情绪上来时先停一停，等彼此都愿意再继续说。";
  const topic = entry?.topic ?? "亲子沟通";
  const relatedEntries = useMemo(() => selectLearningExchangeFeed(projection)?.entries.filter((item) => item.exchange_ref !== exchangeRef) ?? [], [exchangeRef, projection]);
  const loadMoreRelated = () => setRelatedVisible((count) => Math.min(count + 2, relatedEntries.length));

  useEffect(() => {
    setResponseText(interaction?.responseText ?? "");
  }, [interaction?.responseText]);

  const saveResponse = () => {
    if (!responseText.trim()) return;
    saveCommunityResponseDraft(exchangeRef, responseText);
    setSaved(true);
  };

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled" refreshControl={<FamilyRefreshControl />} onScroll={({ nativeEvent }) => { if (nativeEvent.layoutMeasurement.height + nativeEvent.contentOffset.y >= nativeEvent.contentSize.height - 140) loadMoreRelated(); }} scrollEventThrottle={250}>
        <View style={styles.topBar}><Pressable onPress={() => router.back()} style={styles.topBack}><IconSymbol name="chevron.left" size={26} color="#22272D" /></Pressable><Text style={styles.topTitle}>动态详情</Text><Text style={styles.topMore}>•••</Text></View>
        <View style={styles.authorRow}><View style={styles.avatar}><IconSymbol name="person.crop.circle.fill" size={43} color="#F28C45" /></View><View style={styles.authorCopy}><View style={styles.authorNameLine}><Text style={[styles.authorName, { color: colors.text }]}>一位成长中的家长</Text><Text style={styles.reviewedTag}>经审核摘要</Text></View><Text style={[styles.authorMeta, { color: colors.muted }]}>家庭经验 · #{topic}</Text></View><Pressable onPress={() => toggleCommunityFollow(exchangeRef)} style={({ pressed }) => [styles.followButton, { borderColor: colors.tint, backgroundColor: interaction?.following ? colors.tint : colors.background }, pressed && styles.pressed]}><Text style={[styles.followText, { color: interaction?.following ? "#FFFFFF" : colors.tint }]}>{interaction?.following ? "已关注" : "关注"}</Text></Pressable></View>

        <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
        <Text style={[styles.summary, { color: colors.text }]}>{summary}</Text>
        <View style={styles.mediaPanel}><IconSymbol name={topic === "家庭阅读" ? "book.fill" : "message.fill"} size={46} color="#2563EB" /><View style={styles.mediaCopy}><Text style={styles.mediaTitle}>{topic}</Text><Text style={styles.mediaText}>来自一个家庭日常的经验片段</Text></View></View>

        <View style={[styles.sourceCard, { backgroundColor: colors.surface, borderColor: colors.border }]}><View style={[styles.sourceIcon, { backgroundColor: "#16866D16" }]}><IconSymbol name="shield.fill" size={24} color={colors.success} /></View><View style={styles.sourceCopy}><Text style={[styles.sourceTitle, { color: colors.text }]}>内容怎么理解</Text><Text style={[styles.sourceText, { color: colors.muted }]}>这是作者对自己家庭经历的描述，属于个人视角；它不是对其他家庭的结论，也不证明教育效果。</Text></View></View>

        <View style={[styles.actionBar, { borderColor: colors.border }]}><Pressable onPress={() => toggleCommunityBookmark(exchangeRef)} style={({ pressed }) => [styles.actionItem, pressed && styles.pressed]}><IconSymbol name="bookmark.fill" size={22} color={interaction?.bookmarked ? colors.tint : colors.muted} /><Text style={[styles.actionText, { color: interaction?.bookmarked ? colors.tint : colors.muted }]}>{interaction?.bookmarked ? "已收藏" : "收藏"}</Text></Pressable><View style={[styles.actionDivider, { backgroundColor: colors.border }]} /><View style={styles.actionItem}><IconSymbol name="message.fill" size={22} color={colors.muted} /><Text style={[styles.actionText, { color: colors.muted }]}>写下我的想法</Text></View><View style={[styles.actionDivider, { backgroundColor: colors.border }]} /><Pressable onPress={() => router.push("/ui/UI-25" as Href)} style={({ pressed }) => [styles.actionItem, pressed && styles.pressed]}><IconSymbol name="person.2.fill" size={22} color={colors.muted} /><Text style={[styles.actionText, { color: colors.muted }]}>返回社区</Text></Pressable></View>

        <View style={styles.sectionHeading}><Text style={[styles.sectionTitle, { color: colors.text }]}>其他家长的观点</Text><Text style={[styles.sectionHint, { color: colors.muted }]}>观点不是事实</Text></View>
        <View style={[styles.emptyComments, { backgroundColor: colors.surface, borderColor: colors.border }]}><IconSymbol name="message.fill" size={27} color={colors.muted} /><View style={styles.emptyCopy}><Text style={[styles.emptyTitle, { color: colors.text }]}>当前没有公开评论数据</Text><Text style={[styles.emptyText, { color: colors.muted }]}>你可以先写下自己的想法，只保存在家庭空间，不会公开回复或通知作者。</Text></View></View>

        <View style={[styles.responseCard, { backgroundColor: colors.surface, borderColor: colors.border }]}><View style={styles.responseHeader}><Text style={[styles.responseTitle, { color: colors.text }]}>我的回应草稿</Text><Text style={[styles.counter, { color: colors.muted }]}>{responseText.length}/300</Text></View><TextInput value={responseText} onChangeText={(value) => { setResponseText(value.slice(0, 300)); setSaved(false); }} placeholder="写下这段经验给你的启发，或你想继续观察的事……" placeholderTextColor={colors.muted} style={[styles.responseInput, { color: colors.text }]} multiline textAlignVertical="top" /><Pressable disabled={!responseText.trim()} onPress={saveResponse} style={({ pressed }) => [styles.saveResponse, { backgroundColor: responseText.trim() ? colors.tint : colors.border }, pressed && responseText.trim() && styles.pressed]}><IconSymbol name="lock.fill" size={18} color="#FFFFFF" /><Text style={styles.saveResponseText}>{saved ? "已保存到家庭空间" : "保存私有回应"}</Text></Pressable></View>
        {relatedEntries.length ? <View style={styles.relatedSection}><Text style={[styles.sectionTitle, { color: colors.text }]}>继续浏览其他经验</Text>{relatedEntries.slice(0, relatedVisible).map((item) => <Pressable key={item.exchange_ref} onPress={() => router.push(`/ui/UI-27?exchangeRef=${encodeURIComponent(item.exchange_ref)}` as Href)} style={[styles.relatedCard, { backgroundColor: colors.surface, borderColor: colors.border }]}><Text style={[styles.relatedTopic, { color: colors.tint }]}>#{item.topic}</Text><Text style={[styles.relatedTitle, { color: colors.text }]}>{item.title}</Text></Pressable>)}{relatedVisible < relatedEntries.length ? <Text style={[styles.relatedLoading, { color: colors.muted }]}>继续下滑以加载更多经验</Text> : null}</View> : null}

        <View style={[styles.boundary, { borderColor: colors.border }]}><IconSymbol name="lock.fill" size={19} color={colors.success} /><Text style={[styles.boundaryText, { color: colors.muted }]}>关注、收藏和回应都是当前家庭的私有草稿，不会增加公共计数、发送通知或联系作者。</Text></View>
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 16, paddingTop: 14, paddingBottom: 42, gap: 14 }, topBar: { minHeight: 40, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, topBack: { width: 38, height: 38, alignItems: "flex-start", justifyContent: "center" }, topTitle: { color: "#22272D", fontSize: 19, lineHeight: 26, fontWeight: "900" }, topMore: { color: "#22272D", fontSize: 18, lineHeight: 20, fontWeight: "900" }, authorRow: { flexDirection: "row", alignItems: "center", gap: 10 }, avatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: "#F28C4518", alignItems: "center", justifyContent: "center" }, authorCopy: { flex: 1, gap: 3 }, authorNameLine: { flexDirection: "row", alignItems: "center", gap: 6 }, authorName: { fontSize: 14, lineHeight: 20, fontWeight: "900" }, reviewedTag: { color: "#16866D", backgroundColor: "#16866D14", borderRadius: 7, paddingHorizontal: 6, paddingVertical: 2, fontSize: 8, lineHeight: 11, fontWeight: "900" }, authorMeta: { fontSize: 10, lineHeight: 15 }, followButton: { minHeight: 34, borderWidth: 1.5, borderRadius: 17, paddingHorizontal: 15, alignItems: "center", justifyContent: "center" }, followText: { fontSize: 11, lineHeight: 16, fontWeight: "900" },
  title: { fontSize: 23, lineHeight: 32, fontWeight: "900" }, summary: { fontSize: 14, lineHeight: 24, fontWeight: "600" }, mediaPanel: { minHeight: 160, borderRadius: 23, backgroundColor: "#E8F2FF", padding: 22, flexDirection: "row", alignItems: "center", gap: 16 }, mediaCopy: { flex: 1, gap: 5 }, mediaTitle: { color: "#09295A", fontSize: 19, lineHeight: 26, fontWeight: "900" }, mediaText: { color: "#5B7091", fontSize: 12, lineHeight: 18 },
  sourceCard: { minHeight: 102, borderWidth: 1, borderRadius: 20, padding: 14, flexDirection: "row", alignItems: "flex-start", gap: 10 }, sourceIcon: { width: 45, height: 45, borderRadius: 15, alignItems: "center", justifyContent: "center" }, sourceCopy: { flex: 1, gap: 4 }, sourceTitle: { fontSize: 13, lineHeight: 18, fontWeight: "900" }, sourceText: { fontSize: 11, lineHeight: 18 },
  actionBar: { minHeight: 68, borderTopWidth: 1, borderBottomWidth: 1, flexDirection: "row", alignItems: "center", justifyContent: "space-evenly" }, actionItem: { flex: 1, alignItems: "center", justifyContent: "center", gap: 4 }, actionText: { fontSize: 9, lineHeight: 13, fontWeight: "800", textAlign: "center" }, actionDivider: { width: 1, height: 28 }, sectionHeading: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" }, sectionTitle: { fontSize: 17, lineHeight: 24, fontWeight: "900" }, sectionHint: { fontSize: 10, lineHeight: 15 },
  emptyComments: { minHeight: 92, borderWidth: 1, borderRadius: 19, padding: 14, flexDirection: "row", alignItems: "center", gap: 11 }, emptyCopy: { flex: 1, gap: 3 }, emptyTitle: { fontSize: 12, lineHeight: 17, fontWeight: "900" }, emptyText: { fontSize: 10, lineHeight: 16 }, responseCard: { minHeight: 196, borderWidth: 1, borderRadius: 20, padding: 14, gap: 9 }, responseHeader: { flexDirection: "row", justifyContent: "space-between" }, responseTitle: { fontSize: 13, lineHeight: 18, fontWeight: "900" }, counter: { fontSize: 9, lineHeight: 13 }, responseInput: { minHeight: 92, fontSize: 12, lineHeight: 20, paddingVertical: 3 }, saveResponse: { minHeight: 42, borderRadius: 16, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6 }, saveResponseText: { color: "#FFFFFF", fontSize: 11, lineHeight: 16, fontWeight: "900" }, relatedSection: { gap: 8 }, relatedCard: { minHeight: 68, borderWidth: 1, borderRadius: 17, padding: 12, gap: 3 }, relatedTopic: { fontSize: 9, lineHeight: 13, fontWeight: "900" }, relatedTitle: { fontSize: 12, lineHeight: 18, fontWeight: "900" }, relatedLoading: { textAlign: "center", fontSize: 10, lineHeight: 15, paddingVertical: 6 }, boundary: { minHeight: 68, borderTopWidth: 1, paddingTop: 14, flexDirection: "row", alignItems: "flex-start", gap: 8 }, boundaryText: { flex: 1, fontSize: 11, lineHeight: 17 }, pressed: { opacity: 0.82, transform: [{ scale: 0.98 }] },
});
