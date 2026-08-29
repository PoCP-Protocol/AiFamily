import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";

const DIMENSIONS = [
  { label: "亲子沟通", icon: "message.fill" as const, color: "#4D99F3", bg: "#F1F8FF" },
  { label: "学习习惯", icon: "book.fill" as const, color: "#46A66B", bg: "#F4FBF4" },
  { label: "情绪管理", icon: "heart.fill" as const, color: "#F18423", bg: "#FFF8ED" },
  { label: "自律能力", icon: "shield.fill" as const, color: "#8054D6", bg: "#F8F5FF" },
  { label: "手机依赖", icon: "phone.fill" as const, color: "#3881ED", bg: "#F3F8FF" },
] as const;

const EXAMPLE_ANSWERS = ["经常主动分享", "偶尔分享", "很少分享", "几乎不分享"];

export default function GrowthAssessmentEntryScreen() {
  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.topBar}>
          <Pressable accessibilityRole="button" accessibilityLabel="返回" onPress={() => router.back()} style={({ pressed }) => [styles.backButton, pressed && styles.pressed]}>
            <IconSymbol name="chevron.left" size={27} color="#22272E" />
          </Pressable>
          <Text style={styles.topTitle}>家庭成长体检</Text>
          <View style={styles.moreCircle}><Text style={styles.moreText}>•••</Text></View>
        </View>

        <View style={styles.hero}>
          <View style={styles.heroOrbs}><View style={styles.orbOne} /><View style={styles.orbTwo} /><View style={styles.familyFigure}><View style={styles.parentHead} /><View style={styles.childHead} /></View></View>
          <Text style={styles.heroTitle}>3分钟了解{`\n`}孩子成长状态</Text>
          <Text style={styles.heroDescription}>先做一次家庭体检，{`\n`}找到最值得优先解决的问题</Text>
          <Pressable accessibilityRole="button" accessibilityLabel="立即开始测评" onPress={() => router.push("/ui/UI-02" as Href)} style={({ pressed }) => [styles.heroButton, pressed && styles.pressed]}>
            <Text style={styles.heroButtonText}>立即开始测评</Text>
          </Pressable>
          <Text style={styles.step}>第 1 / 5 步</Text>
        </View>

        <Text style={styles.sectionTitle}>5大维度快速评估</Text>
        <View style={styles.dimensionGrid}>
          {DIMENSIONS.map((dimension) => (
            <View key={dimension.label} style={[styles.dimensionCard, { backgroundColor: dimension.bg }]}>
              <IconSymbol name={dimension.icon} size={34} color={dimension.color} />
              <Text style={styles.dimensionLabel}>{dimension.label}</Text>
            </View>
          ))}
        </View>

        <View style={styles.questionCard}>
          <Text style={styles.questionTitle}>示例问题</Text>
          <Text style={styles.question}>孩子最近愿意主动和你分享学校里的事吗？</Text>
          {EXAMPLE_ANSWERS.map((answer) => (
            <View key={answer} style={styles.answerRow}><View style={styles.radio} /><Text style={styles.answer}>{answer}</Text></View>
          ))}
        </View>
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 20, paddingBottom: 34, backgroundColor: "#FFFFFF" },
  topBar: { minHeight: 66, alignItems: "center", flexDirection: "row", justifyContent: "space-between" },
  backButton: { width: 44, height: 44, justifyContent: "center", alignItems: "flex-start" },
  topTitle: { color: "#20242A", fontSize: 20, lineHeight: 27, fontWeight: "900" },
  moreCircle: { width: 25, height: 25, borderRadius: 13, borderWidth: 2, borderColor: "#2B3036", alignItems: "center", justifyContent: "center" },
  moreText: { color: "#2B3036", fontSize: 11, lineHeight: 11, fontWeight: "900", letterSpacing: -1 },
  hero: { minHeight: 314, paddingHorizontal: 23, paddingTop: 34, borderRadius: 17, overflow: "hidden", backgroundColor: "#E8F2FF" },
  heroOrbs: { position: "absolute", right: -3, top: 0, width: 220, height: 242 },
  orbOne: { position: "absolute", right: -58, top: 14, width: 220, height: 220, borderRadius: 110, backgroundColor: "#B9DCFF80" },
  orbTwo: { position: "absolute", right: 4, top: 78, width: 130, height: 130, borderRadius: 65, backgroundColor: "#D6EAFE90" },
  familyFigure: { position: "absolute", right: 23, bottom: 0, width: 107, height: 132, borderTopLeftRadius: 50, borderTopRightRadius: 50, backgroundColor: "#F2B875" },
  parentHead: { position: "absolute", right: 20, top: -37, width: 67, height: 67, borderRadius: 34, backgroundColor: "#825A3F" },
  childHead: { position: "absolute", left: -18, top: 39, width: 48, height: 48, borderRadius: 24, backgroundColor: "#74422D" },
  heroTitle: { color: "#09295A", fontSize: 31, lineHeight: 41, fontWeight: "900", zIndex: 1 },
  heroDescription: { color: "#5B7091", fontSize: 15, lineHeight: 22, fontWeight: "700", marginTop: 17, zIndex: 1 },
  heroButton: { minHeight: 52, marginTop: 22, borderRadius: 27, backgroundColor: "#2563EB", justifyContent: "center", alignItems: "center", zIndex: 1 },
  heroButtonText: { color: "#FFFFFF", fontSize: 18, lineHeight: 25, fontWeight: "900" },
  step: { alignSelf: "center", color: "#536A8B", fontSize: 14, lineHeight: 20, fontWeight: "900", marginTop: 14 },
  sectionTitle: { color: "#2C3138", fontSize: 17, lineHeight: 24, fontWeight: "900", marginTop: 22, marginBottom: 10 },
  dimensionGrid: { flexDirection: "row", flexWrap: "wrap", justifyContent: "center", gap: 10 },
  dimensionCard: { width: "30.5%", minHeight: 91, borderRadius: 15, alignItems: "center", justifyContent: "center", gap: 7, borderWidth: 1, borderColor: "#EAF0F4" },
  dimensionLabel: { color: "#454B53", fontSize: 13, lineHeight: 18, fontWeight: "800" },
  questionCard: { marginTop: 18, borderWidth: 1, borderColor: "#E8EDF2", borderRadius: 16, paddingHorizontal: 17, paddingTop: 16, paddingBottom: 12 },
  questionTitle: { color: "#333940", fontSize: 15, lineHeight: 21, fontWeight: "900" },
  question: { color: "#353B43", fontSize: 14, lineHeight: 21, fontWeight: "700", marginTop: 9, marginBottom: 8 },
  answerRow: { minHeight: 35, flexDirection: "row", alignItems: "center", gap: 9 },
  radio: { width: 19, height: 19, borderRadius: 10, borderWidth: 2, borderColor: "#E0E5EA" },
  answer: { color: "#7F8994", fontSize: 14, lineHeight: 20 },
  pressed: { opacity: 0.86, transform: [{ scale: 0.985 }] },
});
