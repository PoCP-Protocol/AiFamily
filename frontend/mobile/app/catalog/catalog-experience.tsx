import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { familyApi } from "@/lib/family/family-api-client";
import type { FamilyApiCommerceProductsProjection } from "@/lib/family/family-api-projections";
import { createSyntheticMultimodalAdapter, type ExperienceMediaKind, type ExperienceMediaStatus, type MultimodalAdapter } from "@/lib/family/multimodal-api-contracts";
import type { ServiceOfferingDto } from "@/lib/family/service-api-contracts";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { classifyCatalogError, mapRemoteProducts, type CatalogProduct } from "./catalog-contract";
import { mapServiceOfferings } from "../services/service-contract";

export type CatalogExperienceMode = "all" | "products";
export type CatalogLoadState = "idle" | "loading" | "ready" | "synthetic" | "empty" | "denied" | "error";

type CatalogService = {
  ref: string;
  title: string;
  summary: string;
  provider: string;
  channel: string;
  provenance: "REMOTE" | "SYNTHETIC";
  accent: string;
};

const NEED_OPTIONS = [
  { id: "COMMUNICATION", label: "亲子沟通", prompt: "找一个更容易开始的对话" },
  { id: "EMOTION", label: "情绪陪伴", prompt: "先让家里喘口气" },
  { id: "STUDY", label: "学习节奏", prompt: "把催促变成一个小步骤" },
  { id: "FAMILY", label: "家庭关系", prompt: "留一点彼此靠近的时间" },
] as const;

const MEDIA_OPTIONS: readonly { kind: ExperienceMediaKind; label: string; icon: "message.fill" | "photo.fill" | "book.fill" }[] = [
  { kind: "VOICE", label: "语音说说", icon: "message.fill" },
  { kind: "IMAGE", label: "上传一张图", icon: "photo.fill" },
  { kind: "TEXT", label: "文字记录", icon: "book.fill" },
];

const SYNTHETIC_PRODUCTS: readonly CatalogProduct[] = [
  {
    ref: "SYNTHETIC_PARENT_DIALOGUE",
    title: "亲子沟通小练习（演示）",
    summary: "从一段具体对话开始，给家庭一个不费力的尝试。",
    category: "COURSE",
    delivery: ["家庭行动卡", "文字回看"],
    provenance: "SYNTHETIC",
    accent: "#2563EB",
  },
  {
    ref: "SYNTHETIC_FAMILY_READING",
    title: "家庭共读工具包（演示）",
    summary: "把共读放进日常，不用数量评价孩子。",
    category: "TOOL",
    delivery: ["共读卡", "家庭小结"],
    provenance: "SYNTHETIC",
    accent: "#F28C45",
  },
];

const SYNTHETIC_SERVICES: readonly CatalogService[] = [
  {
    ref: "SYNTHETIC_FAMILY_SUPPORT",
    title: "家庭支持顾问（演示）",
    summary: "先听见家庭当前的难处，再一起决定是否需要继续。",
    provider: "家庭支持团队",
    channel: "文字或视频待确认",
    provenance: "SYNTHETIC",
    accent: "#16866D",
  },
];

export default function CatalogExperienceScreen({ mode = "all" }: { mode?: CatalogExperienceMode }) {
  const colors = useColors();
  const session = useFamilyApiSession();
  const [loadState, setLoadState] = useState<CatalogLoadState>("idle");
  const [loadMessage, setLoadMessage] = useState<string | null>(null);
  const [products, setProducts] = useState<CatalogProduct[]>([]);
  const [services, setServices] = useState<CatalogService[]>([]);
  const [need, setNeed] = useState<(typeof NEED_OPTIONS)[number]["id"] | null>(null);
  const [query, setQuery] = useState("");
  const [mediaKind, setMediaKind] = useState<ExperienceMediaKind | null>(null);
  const [mediaStatus, setMediaStatus] = useState<ExperienceMediaStatus>("NOT_REQUESTED");
  const [mediaAdapter, setMediaAdapter] = useState<MultimodalAdapter | null>(null);

  useEffect(() => {
    if (session.status === "local_synthetic") {
      setProducts([...SYNTHETIC_PRODUCTS]);
      setServices(mode === "products" ? [] : [...SYNTHETIC_SERVICES]);
      setLoadState("synthetic");
      setLoadMessage(null);
      setMediaAdapter(createSyntheticMultimodalAdapter());
      return;
    }
    setMediaAdapter(null);
    if (session.status !== "connected" || !session.token || !session.selectedFamily) {
      setProducts([]);
      setServices([]);
      setLoadState(session.status === "authentication_required" || session.status === "no_family" ? "denied" : "idle");
      return;
    }
    let active = true;
    setLoadState("loading");
    setLoadMessage(null);
    const familyId = session.selectedFamily.family_id;
    const productRequest = familyApi.getCommerceProducts<FamilyApiCommerceProductsProjection>(session.token, familyId);
    const serviceRequest = mode === "products" ? Promise.resolve<ServiceOfferingDto[]>([]) : familyApi.getServiceOfferings(session.token, familyId);
    Promise.all([productRequest, serviceRequest])
      .then(([catalog, offeringRows]) => {
        if (!active) return;
        const nextProducts = mapRemoteProducts(catalog.products);
        const nextServices = mapServiceOfferings(offeringRows).map((item) => ({ ref: item.ref, title: item.title, summary: item.summary, provider: item.provider, channel: item.channel, provenance: item.provenance, accent: item.accent }));
        setProducts(nextProducts);
        setServices(nextServices);
        setLoadState(nextProducts.length || nextServices.length ? "ready" : "empty");
      })
      .catch((error: unknown) => {
        if (!active) return;
        setProducts([]);
        setServices([]);
        const classified = classifyCatalogError(error);
        setLoadState(classified);
        setLoadMessage(classified === "denied" ? "当前家庭授权或平台策略暂不允许读取目录。" : "目录暂时没有同步成功，可以稍后再试。 ");
      });
    return () => {
      active = false;
    };
  }, [mode, session.selectedFamily, session.status, session.token]);

  const filteredProducts = useMemo(() => filterByNeed(products, query, need), [need, products, query]);
  const filteredServices = useMemo(() => filterByNeed(services, query, need), [need, query, services]);
  const selectedNeed = NEED_OPTIONS.find((item) => item.id === need);

  const startMediaCapture = useCallback(async (kind: ExperienceMediaKind) => {
    setMediaKind(kind);
    setMediaStatus("CONSENT_REQUIRED");
    if (!mediaAdapter) return;
    try {
      const consent = await mediaAdapter.requestConsent(kind);
      setMediaStatus("UPLOADING");
      await mediaAdapter.upload({ kind, uri: `synthetic://${kind.toLowerCase()}-family-need`, consent_ref: consent.consent_ref });
      setMediaStatus("READY");
    } catch {
      setMediaStatus("UPLOAD_FAILED");
    }
  }, [mediaAdapter]);

  const openProduct = (ref: string) => router.push({ pathname: "/catalog/products/[productRef]", params: { productRef: ref } } as Href);
  const openService = (ref: string) => router.push({ pathname: "/services/offerings/[offeringRef]", params: { offeringRef: ref } } as Href);

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView contentContainerStyle={[styles.content, { backgroundColor: colors.background }]} showsVerticalScrollIndicator={false}>
        <View style={styles.topBar}>
          <Pressable accessibilityRole="button" accessibilityLabel="返回" onPress={() => router.back()} style={styles.topBack}>
            <IconSymbol name="chevron.left" size={24} color={colors.text} />
          </Pressable>
          <Text style={[styles.topTitle, { color: colors.text }]}>{mode === "products" ? "成长支持产品" : "按家庭需要找支持"}</Text>
          <View style={styles.topSpacer} />
        </View>

        <View style={[styles.empathyCard, { backgroundColor: "#E8F2FF" }]}>
          <Text style={styles.eyebrow}>We are 伐木累 · We are family</Text>
          <Text style={styles.heroTitle}>这段时间，家庭是不是有点累？</Text>
          <Text style={styles.heroBody}>先不用解决全部。我们先接住这一刻，再一起找一个今天做得到的小步骤。</Text>
          <View style={styles.pathRow}>
            {(["接住情绪", "看懂需要", "选一个小行动"] as const).map((label, index) => <View key={label} style={styles.pathItem}><Text style={styles.pathNumber}>{index + 1}</Text><Text style={styles.pathLabel}>{label}</Text></View>)}
          </View>
        </View>

        <View style={[styles.needCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>先说说现在更想被支持的地方</Text>
          <TextInput accessibilityLabel="家庭需要" value={query} onChangeText={setQuery} placeholder="一句话也可以，不必说得完整" placeholderTextColor={colors.muted} style={[styles.needInput, { color: colors.text, borderColor: colors.border }]} />
          <View style={styles.needChips}>{NEED_OPTIONS.map((option) => <Pressable key={option.id} accessibilityRole="button" onPress={() => setNeed(need === option.id ? null : option.id)} style={({ pressed }) => [styles.needChip, { borderColor: need === option.id ? colors.tint : colors.border, backgroundColor: need === option.id ? `${colors.tint}12` : colors.background }, pressed && styles.pressed]}><Text style={[styles.needChipLabel, { color: need === option.id ? colors.tint : colors.text }]}>{option.label}</Text></Pressable>)}</View>
          <Text style={[styles.helper, { color: colors.muted }]}>{selectedNeed ? `你选择了“${selectedNeed.label}”：${selectedNeed.prompt}。以下只是探索方向，不是对家庭的诊断。` : "选择一个方向，目录会按你的当下需要重新排一排。"}</Text>
        </View>

        <View style={[styles.mediaCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <View style={styles.sectionHeading}><View><Text style={[styles.sectionTitle, { color: colors.text }]}>也可以用你舒服的方式表达</Text><Text style={[styles.helper, { color: colors.muted }]}>文字、语音、图片、音频、视频和互动卡都沿用同一份授权边界。</Text></View><IconSymbol name="star.fill" size={22} color={colors.tint} /></View>
          <View style={styles.mediaOptions}>{MEDIA_OPTIONS.map((option) => <Pressable key={option.kind} accessibilityRole="button" onPress={() => void startMediaCapture(option.kind)} style={({ pressed }) => [styles.mediaOption, { borderColor: mediaKind === option.kind ? colors.tint : colors.border }, pressed && styles.pressed]}><IconSymbol name={option.icon} size={19} color={colors.tint} /><Text style={[styles.mediaLabel, { color: colors.text }]}>{option.label}</Text></Pressable>)}</View>
          {mediaKind ? <Text style={[styles.mediaStatus, { color: mediaStatus === "READY" ? colors.success : colors.muted }]}>{mediaStatusLabel(mediaStatus, mediaAdapter !== null)}</Text> : null}
        </View>

        {loadState === "loading" ? <View style={[styles.notice, { borderColor: colors.border, backgroundColor: colors.surface }]}><ActivityIndicator color={colors.tint} /><Text style={[styles.noticeText, { color: colors.muted }]}>正在把家庭需要和可用支持对上……</Text></View> : null}
        {loadState === "denied" ? <View style={[styles.notice, styles.noticeDenied]}><Text style={styles.noticeTitle}>先保护家庭的选择</Text><Text style={styles.noticeText}>{loadMessage ?? "当前不能读取支持目录；不会用其他家庭的数据代替。"}</Text></View> : null}
        {loadState === "error" ? <View style={[styles.notice, styles.noticeError]}><Text style={styles.noticeTitle}>目录暂时没有回应</Text><Text style={styles.noticeText}>{loadMessage}</Text></View> : null}
        {loadState === "empty" ? <View style={[styles.notice, { borderColor: colors.border, backgroundColor: colors.surface }]}><Text style={[styles.noticeTitle, { color: colors.text }]}>还没有匹配的支持</Text><Text style={[styles.noticeText, { color: colors.muted }]}>可以换一个家庭需要，或先留下这句话，之后再回来。</Text></View> : null}
        {loadState === "synthetic" ? <Text style={[styles.syntheticNotice, { color: colors.muted }]}>当前为本机演示资料；真实环境会使用同样的目录与流程，不会把演示内容当作家庭事实。</Text> : null}

        {mode === "all" && filteredServices.length ? <CatalogSection title="先看服务支持" hint="有人陪你一起梳理" items={filteredServices.map((item) => <ServiceCard key={item.ref} item={item} colors={colors} onOpen={() => openService(item.ref)} />)} /> : null}
        {filteredProducts.length ? <CatalogSection title={mode === "products" ? "支持产品" : "也可以先从一个工具开始"} hint="先了解，再决定" items={filteredProducts.map((item) => <ProductCard key={item.ref} item={item} colors={colors} onOpen={() => openProduct(item.ref)} />)} /> : null}

        <View style={[styles.nextCard, { backgroundColor: "#FFF5E7", borderColor: "#F3D4A0" }]}>
          <Text style={styles.nextTitle}>下一步，不需要一次做完</Text>
          <Text style={styles.nextBody}>看中一个方向后，先生成方案草案；家庭确认之前不会预约、扣款、联系服务方或替你下结论。</Text>
          <Pressable accessibilityRole="button" onPress={() => router.push("/journeys/plan" as Href)} style={({ pressed }) => [styles.nextButton, pressed && styles.pressed]}><Text style={styles.nextButtonText}>去看看方案草案</Text><IconSymbol name="chevron.right" size={18} color="#7D4F00" /></Pressable>
        </View>
        <Text style={[styles.boundary, { color: colors.muted }]}>目录只展示当前家庭有权了解的资料；推荐依据、授权、语言和租户范围由服务端决定。这里不展示家庭总分、排名或比较。</Text>
      </ScrollView>
    </ScreenContainer>
  );
}

function filterByNeed<T extends CatalogProduct | CatalogService>(items: readonly T[], query: string, need: string | null) {
  const normalized = query.trim().toLowerCase();
  return items.filter((item) => !normalized || `${item.title}${item.summary}`.toLowerCase().includes(normalized) || ("provider" in item && item.provider.toLowerCase().includes(normalized))).filter((item) => !need || needMatches(item, need));
}

function needMatches(item: CatalogProduct | CatalogService, need: string) {
  const value = `${item.title}${item.summary}`;
  if (need === "COMMUNICATION") return /沟通|对话|关系/.test(value);
  if (need === "EMOTION") return /情绪|陪伴|喘口气/.test(value);
  if (need === "STUDY") return /学习|阅读|节奏|习惯/.test(value);
  return /家庭|关系|共读/.test(value);
}

function CatalogSection({ title, hint, items }: { title: string; hint: string; items: React.ReactNode[] }) {
  const colors = useColors();
  return <View style={styles.section}><View style={styles.sectionHeading}><Text style={[styles.sectionTitle, { color: colors.text }]}>{title}</Text><Text style={[styles.sectionHint, { color: colors.muted }]}>{hint}</Text></View>{items}</View>;
}

function ProductCard({ item, colors, onOpen }: { item: CatalogProduct; colors: ReturnType<typeof useColors>; onOpen: () => void }) {
  return <Pressable accessibilityRole="button" accessibilityLabel={`了解${item.title}`} onPress={onOpen} style={({ pressed }) => [styles.itemCard, { backgroundColor: colors.surface, borderColor: colors.border }, pressed && styles.pressed]}><View style={[styles.itemIcon, { backgroundColor: `${item.accent}18` }]}><IconSymbol name={item.category === "COURSE" ? "book.fill" : item.category === "ASSESSMENT" ? "doc.text.fill" : "gift.fill"} size={24} color={item.accent} /></View><View style={styles.itemCopy}><View style={styles.itemHeading}><Text style={[styles.itemTitle, { color: colors.text }]} numberOfLines={2}>{item.title}</Text><Text style={[styles.sourceBadge, { color: item.provenance === "SYNTHETIC" ? colors.muted : colors.success }]}>{item.provenance === "SYNTHETIC" ? "演示资料" : "可了解"}</Text></View><Text style={[styles.itemSummary, { color: colors.muted }]} numberOfLines={2}>{item.summary}</Text><View style={styles.deliveryRow}>{item.delivery.slice(0, 3).map((tag) => <Text key={tag} style={[styles.deliveryTag, { color: item.accent, borderColor: `${item.accent}55` }]}>{tag}</Text>)}</View><Text style={[styles.itemAction, { color: colors.tint }]}>查看支持边界与下一步 ›</Text></View></Pressable>;
}

function ServiceCard({ item, colors, onOpen }: { item: CatalogService; colors: ReturnType<typeof useColors>; onOpen: () => void }) {
  return <Pressable accessibilityRole="button" accessibilityLabel={`了解${item.title}`} onPress={onOpen} style={({ pressed }) => [styles.itemCard, { backgroundColor: colors.surface, borderColor: colors.border }, pressed && styles.pressed]}><View style={[styles.itemIcon, { backgroundColor: `${item.accent}18` }]}><IconSymbol name="person.2.fill" size={24} color={item.accent} /></View><View style={styles.itemCopy}><View style={styles.itemHeading}><Text style={[styles.itemTitle, { color: colors.text }]} numberOfLines={2}>{item.title}</Text><Text style={[styles.sourceBadge, { color: item.provenance === "SYNTHETIC" ? colors.muted : colors.success }]}>{item.provenance === "SYNTHETIC" ? "演示资料" : "服务资料"}</Text></View><Text style={[styles.itemSummary, { color: colors.muted }]} numberOfLines={2}>{item.summary}</Text><Text style={[styles.itemMeta, { color: colors.muted }]}>{item.provider} · {item.channel}</Text><Text style={[styles.itemAction, { color: colors.tint }]}>先了解，再决定 ›</Text></View></Pressable>;
}

function mediaStatusLabel(status: ExperienceMediaStatus, synthetic: boolean) {
  if (status === "READY") return synthetic ? "演示媒体已就绪（仅本机内存，不写入家庭事实）" : "已获得授权；真实媒体处理将由服务端确认";
  if (status === "UPLOADING") return "正在准备媒体……";
  if (status === "UPLOAD_FAILED") return "媒体准备失败；可以改用文字，或稍后再试。";
  if (status === "CONSENT_REQUIRED") return synthetic ? "需要你的同意后才会使用演示媒体。" : "需要先确认媒体授权；当前没有猜测任何上传接口。";
  return "媒体输入尚未开始。";
}

const styles = StyleSheet.create({
  content: { padding: 16, paddingTop: 10, paddingBottom: 40, gap: 14 },
  topBar: { minHeight: 44, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  topBack: { width: 40, minHeight: 40, alignItems: "flex-start", justifyContent: "center" },
  topSpacer: { width: 40 },
  topTitle: { fontSize: 20, lineHeight: 28, fontWeight: "900" },
  empathyCard: { borderRadius: 24, padding: 19, gap: 8 },
  eyebrow: { color: "#2563EB", fontSize: 11, lineHeight: 16, fontWeight: "800" },
  heroTitle: { color: "#09295A", fontSize: 24, lineHeight: 32, fontWeight: "900" },
  heroBody: { color: "#4D6382", fontSize: 13, lineHeight: 20 },
  pathRow: { flexDirection: "row", gap: 8, marginTop: 4 },
  pathItem: { flex: 1, minHeight: 44, borderRadius: 14, backgroundColor: "#FFFFFFAA", padding: 7, flexDirection: "row", alignItems: "center", gap: 5 },
  pathNumber: { width: 22, height: 22, borderRadius: 11, backgroundColor: "#2563EB", color: "#FFFFFF", textAlign: "center", lineHeight: 22, fontSize: 11, fontWeight: "900" },
  pathLabel: { flex: 1, color: "#09295A", fontSize: 10, lineHeight: 14, fontWeight: "800" },
  needCard: { borderRadius: 20, borderWidth: 1, padding: 15, gap: 10 },
  sectionTitle: { fontSize: 17, lineHeight: 24, fontWeight: "900" },
  needInput: { minHeight: 48, borderRadius: 14, borderWidth: 1, paddingHorizontal: 12, fontSize: 13, lineHeight: 19 },
  needChips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  needChip: { minHeight: 38, borderRadius: 19, borderWidth: 1, paddingHorizontal: 13, alignItems: "center", justifyContent: "center" },
  needChipLabel: { fontSize: 12, lineHeight: 17, fontWeight: "800" },
  helper: { fontSize: 11, lineHeight: 17 },
  mediaCard: { borderRadius: 20, borderWidth: 1, padding: 15, gap: 11 },
  sectionHeading: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 },
  mediaOptions: { flexDirection: "row", gap: 8 },
  mediaOption: { flex: 1, minHeight: 44, borderRadius: 14, borderWidth: 1, alignItems: "center", justifyContent: "center", gap: 4 },
  mediaLabel: { fontSize: 10, lineHeight: 14, fontWeight: "800" },
  mediaStatus: { fontSize: 11, lineHeight: 17 },
  notice: { minHeight: 62, borderWidth: 1, borderRadius: 17, padding: 13, flexDirection: "row", alignItems: "center", gap: 9 },
  noticeDenied: { borderColor: "#E9C98B", backgroundColor: "#FFF7E8", flexDirection: "column", alignItems: "flex-start" },
  noticeError: { borderColor: "#F2B5A7", backgroundColor: "#FFF0ED", flexDirection: "column", alignItems: "flex-start" },
  noticeTitle: { color: "#7D4F00", fontSize: 13, lineHeight: 18, fontWeight: "900" },
  noticeText: { flex: 1, fontSize: 11, lineHeight: 17 },
  syntheticNotice: { fontSize: 10, lineHeight: 15, textAlign: "center" },
  section: { gap: 10 },
  sectionHint: { fontSize: 11, lineHeight: 16 },
  itemCard: { minHeight: 116, borderRadius: 19, borderWidth: 1, padding: 13, flexDirection: "row", gap: 10 },
  itemIcon: { width: 48, height: 48, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  itemCopy: { flex: 1, gap: 4 },
  itemHeading: { flexDirection: "row", alignItems: "flex-start", gap: 7 },
  itemTitle: { flex: 1, fontSize: 14, lineHeight: 19, fontWeight: "900" },
  sourceBadge: { fontSize: 10, lineHeight: 15, fontWeight: "800" },
  itemSummary: { fontSize: 11, lineHeight: 17 },
  itemMeta: { fontSize: 10, lineHeight: 15 },
  deliveryRow: { flexDirection: "row", flexWrap: "wrap", gap: 5 },
  deliveryTag: { borderWidth: 1, borderRadius: 8, paddingHorizontal: 6, paddingVertical: 2, fontSize: 9, lineHeight: 13 },
  itemAction: { fontSize: 11, lineHeight: 16, fontWeight: "800" },
  nextCard: { borderWidth: 1, borderRadius: 20, padding: 16, gap: 8 },
  nextTitle: { color: "#7D4F00", fontSize: 17, lineHeight: 23, fontWeight: "900" },
  nextBody: { color: "#8A6B39", fontSize: 12, lineHeight: 18 },
  nextButton: { minHeight: 44, borderRadius: 16, backgroundColor: "#F5D99B", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 3, marginTop: 2 },
  nextButtonText: { color: "#7D4F00", fontSize: 13, lineHeight: 18, fontWeight: "900" },
  boundary: { fontSize: 10, lineHeight: 16, textAlign: "center" },
  pressed: { opacity: 0.82, transform: [{ scale: 0.985 }] },
});
