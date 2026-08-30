import { router, type Href } from "expo-router";
import { ScrollView, Pressable, StyleSheet, Text, View } from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { Fonts } from "@/lib/_core/theme";

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
          onPress={() => go("/assessment" as Href)}
          style={({ pressed }) => [styles.hero, { backgroundColor: colors.primary }, pressed && styles.pressed]}
        >
          <View style={styles.heroCopy}>
            <Text style={styles.heroKicker}>从一个真实的小困扰开始</Text>
            <Text style={styles.heroTitle}>说说家庭现在最需要什么</Text>
            <Text style={styles.heroBody}>可以打字、说话或拍下当下的场景，先被听见，再一起决定下一步。</Text>
            <View style={styles.heroAction}>
              <Text style={styles.heroActionText}>开始家庭表达</Text>
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

        <View style={[styles.multimodalHint, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <View style={styles.multimodalIcons}>
            <IconSymbol name="message.fill" size={18} color={colors.primary} />
            <IconSymbol name="photo.fill" size={18} color={colors.trust} />
            <IconSymbol name="video.fill" size={18} color={colors.growth} />
          </View>
          <View style={styles.multimodalCopy}>
            <Text style={[styles.multimodalTitle, { color: colors.text }]}>不必把感受整理成标准答案</Text>
            <Text style={[styles.multimodalBody, { color: colors.muted }]}>文字、语音、图片和视频，都可以成为家庭被理解的入口。</Text>
          </View>
        </View>
      </ScrollView>
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
  pressed: { opacity: 0.86, transform: [{ scale: 0.985 }] },
});
