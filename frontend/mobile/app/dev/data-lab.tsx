import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import {
  UI34_SCENARIO_FIXTURES,
  getUiScenarioFixtureCounts,
  type UiFixtureFilter,
} from "@/dev-fixtures/ui34-scenario";

const STATE_COLOR = { READY: "#16845B", DRAFT: "#B26A00", REVIEW: "#6D55B5" } as const;
const FILTERS: readonly { id: UiFixtureFilter; label: string }[] = [
  { id: "ALL", label: "全部" },
  { id: "READY", label: "就绪" },
  { id: "DRAFT", label: "草稿" },
  { id: "REVIEW", label: "待确认" },
];

export default function UiDataLabScreen() {
  const [filter, setFilter] = useState<UiFixtureFilter>("ALL");
  const counts = useMemo(() => getUiScenarioFixtureCounts(), []);
  const fixtures = useMemo(
    () => filter === "ALL" ? UI34_SCENARIO_FIXTURES : UI34_SCENARIO_FIXTURES.filter((item) => item.state === filter),
    [filter],
  );

  return (
    <ScreenContainer edges={["top", "left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.eyebrow}>DEV FIXTURE · 无外部副作用</Text>
        <Text style={styles.title}>34 屏模拟数据总览</Text>
        <Text style={styles.note}>所有内容只用于界面联调，不是家庭事实、诊断结果或真实服务记录。</Text>
        <View accessibilityLabel="模拟数据状态统计" style={styles.summary}>
          {FILTERS.slice(1).map((item) => (
            <View key={item.id} style={styles.summaryItem}>
              <Text style={[styles.summaryValue, { color: item.id === "ALL" ? "#2563EB" : STATE_COLOR[item.id] }]}>{counts[item.id]}</Text>
              <Text style={styles.summaryLabel}>{item.label}</Text>
            </View>
          ))}
        </View>
        <View accessibilityRole="tablist" style={styles.filters}>
          {FILTERS.map((item) => {
            const selected = filter === item.id;
            return (
              <Pressable
                key={item.id}
                accessibilityRole="tab"
                accessibilityState={{ selected }}
                onPress={() => setFilter(item.id)}
                style={({ pressed }) => [styles.filter, selected && styles.filterActive, pressed && styles.pressed]}
              >
                <Text style={[styles.filterText, selected && styles.filterTextActive]}>{item.label} {counts[item.id]}</Text>
              </Pressable>
            );
          })}
        </View>
        <Text accessibilityLiveRegion="polite" style={styles.resultCount}>当前显示 {fixtures.length} 个界面</Text>
        {fixtures.map((fixture) => (
          <Pressable
            accessibilityLabel={`打开 ${fixture.uiId} ${fixture.headline}`}
            accessibilityRole="link"
            key={fixture.uiId}
            onPress={() => router.push(`/ui/${fixture.uiId}` as Href)}
            style={({ pressed }) => [styles.card, pressed && styles.cardPressed]}
          >
            <View style={styles.row}>
              <Text style={styles.uiId}>{fixture.uiId}</Text>
              <Text style={[styles.state, { color: STATE_COLOR[fixture.state] }]}>{fixture.state}</Text>
            </View>
            <Text style={styles.headline}>{fixture.headline}</Text>
            {fixture.facts.map((fact) => <Text key={fact} style={styles.fact}>• {fact}</Text>)}
            <Text style={styles.action}>{fixture.nextAction} →</Text>
          </Pressable>
        ))}
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { padding: 20, paddingBottom: 60, backgroundColor: "#F6F8FC", gap: 12 },
  eyebrow: { color: "#7B5A00", fontSize: 12, fontWeight: "800" },
  title: { color: "#17233B", fontSize: 28, lineHeight: 36, fontWeight: "900" },
  note: { color: "#5F6B7A", fontSize: 14, lineHeight: 22, marginBottom: 4 },
  summary: { flexDirection: "row", gap: 10 },
  summaryItem: { flex: 1, minHeight: 72, borderRadius: 14, backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "#E2E8F0" },
  summaryValue: { fontSize: 24, lineHeight: 30, fontWeight: "900" },
  summaryLabel: { color: "#64748B", fontSize: 11, fontWeight: "700" },
  filters: { flexDirection: "row", gap: 8, marginTop: 2 },
  filter: { minHeight: 34, paddingHorizontal: 12, borderRadius: 17, alignItems: "center", justifyContent: "center", backgroundColor: "#E9EEF6" },
  filterActive: { backgroundColor: "#2563EB" },
  filterText: { color: "#526173", fontSize: 12, fontWeight: "800" },
  filterTextActive: { color: "#FFFFFF" },
  resultCount: { color: "#64748B", fontSize: 12, fontWeight: "700" },
  pressed: { opacity: 0.8 },
  card: { backgroundColor: "#FFFFFF", borderRadius: 16, padding: 16, borderWidth: 1, borderColor: "#E2E8F0" },
  cardPressed: { opacity: 0.86, transform: [{ scale: 0.995 }] },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  uiId: { color: "#2563EB", fontSize: 13, fontWeight: "900" },
  state: { fontSize: 11, fontWeight: "900" },
  headline: { color: "#1E293B", fontSize: 17, lineHeight: 24, fontWeight: "800", marginTop: 8, marginBottom: 5 },
  fact: { color: "#64748B", fontSize: 13, lineHeight: 20 },
  action: { color: "#2563EB", fontSize: 13, fontWeight: "800", marginTop: 9 },
});
