import * as Haptics from "expo-haptics";
import type { Href } from "expo-router";
import { Stack, router, useLocalSearchParams } from "expo-router";
import { FlatList, Platform, Pressable, StyleSheet, Text, View } from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { useFamilyMobile } from "@/lib/family/family-state";
import { getUiActionPolicy } from "@/lib/family/ui-action-policies";
import { getFamilyScreen } from "@/lib/family/ui-registry";
import { haptic } from "@/lib/haptics";

export default function FamilyUiScreen() {
  const colors = useColors();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { recordUiAction, uiActionReceipts } = useFamilyMobile();
  const screen = getFamilyScreen(id ?? "");

  if (!screen) {
    return (
      <ScreenContainer className="p-6 items-center justify-center">
        <Stack.Screen options={{ title: "页面未找到" }} />
        <Text style={[styles.title, { color: colors.text }]}>没有找到这个家庭页面</Text>
        <Pressable onPress={() => router.replace("/(tabs)" as Href)} style={[styles.primaryButton, { backgroundColor: colors.tint }]}>
          <Text style={styles.primaryButtonText}>回到今天</Text>
        </Pressable>
      </ScreenContainer>
    );
  }

  const policy = getUiActionPolicy(screen.id);
  const actionReceipt = policy ? uiActionReceipts.find((item) => item.screenId === screen.id && item.kind === policy.kind) : undefined;

  const navigatePrimary = () => {
    if (policy && !actionReceipt) {
      recordUiAction(policy, screen.primaryAction);
      haptic.success();
      return;
    }
    if (Platform.OS !== "web") void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    if (screen.primaryTarget) {
      router.push(`/ui/${screen.primaryTarget}` as Href);
    } else {
      router.back();
    }
  };

  return (
    <ScreenContainer>
      <Stack.Screen options={{ headerShown: true, title: screen.title, headerBackTitle: "返回" }} />
      <FlatList
        data={screen.featurePoints}
        keyExtractor={(item) => item}
        contentContainerStyle={styles.content}
        ListHeaderComponent={
          <View style={styles.header}>
            <View style={styles.metaRow}>
              <Text style={[styles.id, { color: colors.tint }]}>{screen.id}</Text>
              <View style={[styles.loopBadge, { backgroundColor: colors.surface, borderColor: colors.border }]}>
                <Text style={[styles.loopText, { color: colors.success }]}>{screen.loop}循环</Text>
              </View>
            </View>
            <Text style={[styles.title, { color: colors.text }]}>{screen.title}</Text>
            <Text style={[styles.subtitle, { color: colors.muted }]}>{screen.subtitle}</Text>
            <View style={[styles.boundary, { backgroundColor: colors.surface, borderColor: colors.border }]}>
              <View style={[styles.boundaryDot, { backgroundColor: colors.tint }]} />
              <Text style={[styles.boundaryText, { color: colors.muted }]}>所有建议都保留来源；家庭确认后才形成行动。</Text>
            </View>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>这个页面会帮助你</Text>
          </View>
        }
        renderItem={({ item, index }) => (
          <View style={[styles.featureRow, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            <View style={[styles.featureNumber, { backgroundColor: colors.background }]}>
              <Text style={[styles.featureNumberText, { color: colors.tint }]}>{index + 1}</Text>
            </View>
            <Text style={[styles.featureText, { color: colors.text }]}>{item}</Text>
          </View>
        )}
        ListFooterComponent={
          <View style={styles.footer}>
            {actionReceipt ? (
              <View style={[styles.actionReceipt, { backgroundColor: colors.surface, borderColor: colors.border }]}>
                <IconSymbol name="checkmark.circle.fill" size={27} color={colors.success} />
                <View style={styles.actionReceiptCopy}>
                  <Text style={[styles.actionReceiptTitle, { color: colors.text }]}>已保存</Text>
                  <Text style={[styles.actionReceiptText, { color: colors.muted }]}>{actionReceipt.message}</Text>
                </View>
              </View>
            ) : null}
            <Pressable
              accessibilityRole="button"
              onPress={navigatePrimary}
              style={({ pressed }) => [styles.primaryButton, { backgroundColor: colors.tint }, pressed && styles.pressed]}
            >
              <Text style={styles.primaryButtonText}>{actionReceipt && screen.primaryTarget ? "继续下一步" : actionReceipt ? "已保存" : screen.primaryAction}</Text>
              {actionReceipt && !screen.primaryTarget ? <IconSymbol name="checkmark.circle.fill" size={20} color="#FFFFFF" /> : <IconSymbol name="chevron.right" size={20} color="#FFFFFF" />}
            </Pressable>
          </View>
        }
      />
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 20, paddingTop: 18, paddingBottom: 34, gap: 12 },
  header: { gap: 12, marginBottom: 6 },
  metaRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  id: { fontSize: 13, lineHeight: 18, fontWeight: "800", letterSpacing: 1 },
  loopBadge: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6 },
  loopText: { fontSize: 12, lineHeight: 16, fontWeight: "700" },
  title: { fontSize: 30, lineHeight: 38, fontWeight: "800" },
  subtitle: { fontSize: 16, lineHeight: 24 },
  boundary: { minHeight: 64, borderWidth: 1, borderRadius: 18, paddingHorizontal: 15, flexDirection: "row", alignItems: "center", gap: 10 },
  boundaryDot: { width: 9, height: 9, borderRadius: 5 },
  boundaryText: { flex: 1, fontSize: 13, lineHeight: 19 },
  sectionTitle: { fontSize: 19, lineHeight: 25, fontWeight: "800", marginTop: 4 },
  featureRow: { minHeight: 70, borderWidth: 1, borderRadius: 18, padding: 14, flexDirection: "row", alignItems: "center", gap: 12 },
  featureNumber: { width: 38, height: 38, borderRadius: 13, alignItems: "center", justifyContent: "center" },
  featureNumberText: { fontSize: 14, lineHeight: 18, fontWeight: "800" },
  featureText: { flex: 1, fontSize: 16, lineHeight: 22, fontWeight: "600" },
  footer: { gap: 12 },
  actionReceipt: { minHeight: 82, borderWidth: 1, borderRadius: 20, padding: 15, flexDirection: "row", alignItems: "center", gap: 12 },
  actionReceiptCopy: { flex: 1, gap: 3 },
  actionReceiptTitle: { fontSize: 16, lineHeight: 21, fontWeight: "800" },
  actionReceiptText: { fontSize: 13, lineHeight: 19 },
  primaryButton: { minHeight: 54, borderRadius: 18, paddingHorizontal: 18, marginTop: 10, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8 },
  primaryButtonText: { color: "#FFFFFF", fontSize: 16, lineHeight: 22, fontWeight: "800" },
  pressed: { opacity: 0.82, transform: [{ scale: 0.98 }] },
});
