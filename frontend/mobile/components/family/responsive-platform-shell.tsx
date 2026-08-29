import type { ReactNode } from "react";
import { Platform, Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from "react-native";
import { usePathname, useRouter } from "expo-router";

import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";

export const FAMILY_PRIMARY_NAV = [
  { label: "今天", route: "/", icon: "house.fill" },
  { label: "成长", route: "/growth", icon: "chart.bar.fill" },
  { label: "发现", route: "/discover", icon: "safari.fill" },
  { label: "服务", route: "/services", icon: "person.2.fill" },
  { label: "我的", route: "/mine", icon: "person.crop.circle.fill" },
] as const;

const FAMILY_SHORTCUTS = [
  { label: "成长测评", route: "/ui/UI-02" },
  { label: "90 天计划", route: "/ui/UI-04" },
  { label: "今日行动", route: "/ui/UI-09" },
  { label: "家庭档案", route: "/ui/UI-33" },
] as const;

export const DESKTOP_SHELL_BREAKPOINT = 760;
export const WIDE_DESKTOP_BREAKPOINT = 1240;
const IPHONE_16_PRO_MAX_WIDTH = 440;
const IPHONE_16_PRO_MAX_HEIGHT = 956;

export function ResponsivePlatformShell({ children }: { children: ReactNode }) {
  const colors = useColors();
  const router = useRouter();
  const pathname = usePathname();
  const { width } = useWindowDimensions();
  const desktop = Platform.OS === "web" && width >= DESKTOP_SHELL_BREAKPOINT;
  const wideDesktop = width >= WIDE_DESKTOP_BREAKPOINT;

  if (!desktop) return <>{children}</>;

  const navigate = (route: string) => router.push(route as never);
  const activeRoute = FAMILY_PRIMARY_NAV.find((item) => item.route === "/" ? pathname === "/" : pathname.startsWith(item.route))?.route;

  return (
    <View style={[styles.shell, { backgroundColor: colors.background }]}>
      <aside style={styles.leftRail as never} aria-label="Family AI 主导航">
        <View style={[styles.leftRailInner, { borderRightColor: colors.border, backgroundColor: colors.surface }]}>
          <Pressable accessibilityRole="button" accessibilityLabel="返回 Family AI 首页" onPress={() => navigate("/")} style={styles.brand}>
            <View style={[styles.brandMark, { backgroundColor: colors.text }]}><Text style={[styles.brandLetter, { color: colors.background }]}>F</Text></View>
            <View><Text style={[styles.brandName, { color: colors.text }]}>Family AI</Text><Text style={[styles.brandTagline, { color: colors.muted }]}>一起成为更好的家</Text></View>
          </Pressable>

          <View style={styles.primaryNav}>
            {FAMILY_PRIMARY_NAV.map((item) => {
              const active = activeRoute === item.route;
              return (
                <Pressable key={item.route} accessibilityRole="link" accessibilityState={{ selected: active }} onPress={() => navigate(item.route)} style={({ pressed }) => [styles.navItem, active && { backgroundColor: `${colors.tint}14` }, pressed && styles.pressed]}>
                  <IconSymbol name={item.icon} size={23} color={active ? colors.tint : colors.text} />
                  <Text style={[styles.navLabel, { color: active ? colors.tint : colors.text }]}>{item.label}</Text>
                </Pressable>
              );
            })}
          </View>

          <View style={[styles.shortcutGroup, { borderTopColor: colors.border }]}>
            <Text style={[styles.groupLabel, { color: colors.muted }]}>常用功能</Text>
            {FAMILY_SHORTCUTS.map((item) => <Pressable key={item.route} accessibilityRole="link" onPress={() => navigate(item.route)} style={({ pressed }) => [styles.shortcut, pressed && styles.pressed]}><Text style={[styles.shortcutText, { color: colors.muted }]}>{item.label}</Text><IconSymbol name="chevron.right" size={16} color={colors.muted} /></Pressable>)}
          </View>

          <Pressable accessibilityRole="button" accessibilityLabel="开始记录家庭成长" onPress={() => navigate("/ui/UI-09")} style={({ pressed }) => [styles.createButton, { backgroundColor: colors.tint }, pressed && styles.pressed]}>
            <Text style={styles.createButtonText}>记录成长</Text>
          </Pressable>
        </View>
      </aside>

      <main style={styles.main as never} aria-label="Family AI 主要内容">
        <View style={[styles.stageFrame, { backgroundColor: '#ECF3FB' }]}>
          <View style={[styles.stage, { borderColor: colors.border, backgroundColor: colors.background }]}>{children}</View>
        </View>
      </main>

      {wideDesktop ? <aside style={styles.rightRail as never} aria-label="家庭成长上下文">
        <ScrollView contentContainerStyle={styles.rightRailInner} showsVerticalScrollIndicator={false}>
          <View style={[styles.contextCard, { borderColor: colors.border, backgroundColor: colors.surface }]}>
            <View style={styles.contextHeader}><View style={[styles.familyAvatar, { backgroundColor: `${colors.tint}18` }]}><IconSymbol name="person.2.fill" size={22} color={colors.tint} /></View><View><Text style={[styles.contextEyebrow, { color: colors.muted }]}>当前家庭</Text><Text style={[styles.contextTitle, { color: colors.text }]}>我们的成长空间</Text></View></View>
            <Text style={[styles.contextBody, { color: colors.muted }]}>App 与 Web 使用同一 Family Account、同一成长旅程和同一服务回执。</Text>
          </View>

          <View style={[styles.contextCard, { borderColor: colors.border, backgroundColor: colors.surface }]}>
            <Text style={[styles.contextEyebrow, { color: colors.tint }]}>今晚一件事</Text>
            <Text style={[styles.contextTitle, { color: colors.text }]}>先听完，再回应</Text>
            <Text style={[styles.contextBody, { color: colors.muted }]}>不用一次解决所有问题，先完成一次可记录的小行动。</Text>
            <Pressable accessibilityRole="link" onPress={() => navigate("/ui/UI-09")} style={styles.contextLink}><Text style={[styles.contextLinkText, { color: colors.tint }]}>打开今日行动</Text><IconSymbol name="chevron.right" size={16} color={colors.tint} /></Pressable>
          </View>

          <View style={[styles.trustNote, { backgroundColor: `${colors.tint}0B` }]}>
            <IconSymbol name="shield.fill" size={18} color={colors.tint} />
            <Text style={[styles.trustText, { color: colors.muted }]}>家庭记录默认私密。AI 建议不等于事实、决定或行动。</Text>
          </View>
        </ScrollView>
      </aside> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  // 原生 <main>/<aside> 默认 display:block，RN 的 flex 数字不会自动附带 display，需显式声明列布局撑满高度。
  shell: { flex: 1, flexDirection: "row", minHeight: "100vh" as never },
  leftRail: { display: "flex" as never, flexDirection: "column", width: 232, minWidth: 232 },
  leftRailInner: { position: "fixed" as never, left: 0, top: 0, bottom: 0, width: 232, display: "flex" as never, flexDirection: "column", paddingHorizontal: 16, paddingVertical: 22, borderRightWidth: StyleSheet.hairlineWidth },
  brand: { flexDirection: "row", alignItems: "center", gap: 11, paddingHorizontal: 8, marginBottom: 24 },
  brandMark: { width: 40, height: 40, borderRadius: 13, alignItems: "center", justifyContent: "center" },
  brandLetter: { fontSize: 22, fontWeight: "900" },
  brandName: { fontSize: 18, lineHeight: 23, fontWeight: "900" },
  brandTagline: { fontSize: 11, lineHeight: 16, fontWeight: "600" },
  primaryNav: { gap: 6 },
  navItem: { minHeight: 50, paddingHorizontal: 14, borderRadius: 14, flexDirection: "row", alignItems: "center", gap: 14 },
  navLabel: { fontSize: 16, lineHeight: 22, fontWeight: "800" },
  shortcutGroup: { marginTop: 20, paddingTop: 18, borderTopWidth: StyleSheet.hairlineWidth, gap: 4 },
  groupLabel: { paddingHorizontal: 12, marginBottom: 6, fontSize: 11, lineHeight: 16, fontWeight: "800", letterSpacing: 1 },
  shortcut: { minHeight: 38, paddingHorizontal: 12, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  shortcutText: { fontSize: 13, lineHeight: 18, fontWeight: "700" },
  createButton: { position: "absolute", left: 18, right: 18, bottom: 24, minHeight: 46, borderRadius: 13, alignItems: "center", justifyContent: "center" },
  createButtonText: { color: "#FFFFFF", fontSize: 14, lineHeight: 20, fontWeight: "900" },
  main: { display: "flex" as never, flexDirection: "column", flex: 1, minWidth: 0, minHeight: "100vh" as never, alignItems: "center", justifyContent: "center", paddingHorizontal: 32, paddingVertical: 24 },
  stageFrame: { width: IPHONE_16_PRO_MAX_WIDTH + 28, minHeight: IPHONE_16_PRO_MAX_HEIGHT + 28, borderRadius: 38, padding: 14, shadowColor: "#2B5C90", shadowOpacity: 0.16, shadowRadius: 28, shadowOffset: { width: 0, height: 18 }, elevation: 10 },
  stage: { width: IPHONE_16_PRO_MAX_WIDTH, height: IPHONE_16_PRO_MAX_HEIGHT, alignSelf: "center", overflow: "hidden", borderWidth: StyleSheet.hairlineWidth, borderRadius: 30 },
  rightRail: { display: "flex" as never, flexDirection: "column", width: 310, minWidth: 310 },
  rightRailInner: { paddingTop: 24, paddingRight: 24, paddingBottom: 32, gap: 14 },
  contextCard: { borderWidth: StyleSheet.hairlineWidth, borderRadius: 17, padding: 16, gap: 10 },
  contextHeader: { flexDirection: "row", alignItems: "center", gap: 10 },
  familyAvatar: { width: 42, height: 42, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  contextEyebrow: { fontSize: 11, lineHeight: 16, fontWeight: "800" },
  contextTitle: { fontSize: 15, lineHeight: 21, fontWeight: "900" },
  contextBody: { fontSize: 12, lineHeight: 19, fontWeight: "600" },
  contextLink: { minHeight: 34, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  contextLinkText: { fontSize: 13, lineHeight: 18, fontWeight: "900" },
  trustNote: { borderRadius: 15, padding: 14, flexDirection: "row", alignItems: "flex-start", gap: 9 },
  trustText: { flex: 1, fontSize: 11, lineHeight: 18, fontWeight: "600" },
  pressed: { opacity: 0.72 },
});
