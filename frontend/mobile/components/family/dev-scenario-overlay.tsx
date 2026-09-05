import type { Href } from "expo-router";
import { router, usePathname } from "expo-router";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { getUiScenarioFixtureForPathname } from "@/dev-fixtures/ui34-scenario";

const STATE_COLOR = { READY: "#16845B", DRAFT: "#B26A00", REVIEW: "#6D55B5" } as const;

export function DevScenarioOverlay() {
  const pathname = usePathname();
  const [expanded, setExpanded] = useState(false);
  const fixture = getUiScenarioFixtureForPathname(pathname);

  if (process.env.NODE_ENV === "production" || !fixture) return null;

  return (
    <View pointerEvents="box-none" style={styles.overlay}>
      <View style={styles.panel}>
        <Pressable
          accessibilityLabel={`${fixture.uiId} 开发模拟数据`}
          accessibilityRole="button"
          onPress={() => setExpanded((value) => !value)}
          style={({ pressed }) => [styles.header, pressed && styles.pressed]}
        >
          <Text style={styles.fixtureLabel}>DEV DATA</Text>
          <Text style={styles.uiId}>{fixture.uiId}</Text>
          <Text style={[styles.state, { color: STATE_COLOR[fixture.state] }]}>{fixture.state}</Text>
          <Text style={styles.toggle}>{expanded ? "收起" : "展开"}</Text>
        </Pressable>
        {expanded ? (
          <View style={styles.body}>
            <Text style={styles.headline}>{fixture.headline}</Text>
            {fixture.facts.map((fact) => <Text key={fact} style={styles.fact}>• {fact}</Text>)}
            <View style={styles.footer}>
              <Text style={styles.boundary}>仅开发展示 · 无外部副作用</Text>
              <Pressable
                accessibilityRole="link"
                onPress={() => router.push("/dev/data-lab" as Href)}
              >
                <Text style={styles.link}>查看 34 屏 →</Text>
              </Pressable>
            </View>
          </View>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: { ...StyleSheet.absoluteFillObject, alignItems: "flex-end", justifyContent: "flex-start", paddingTop: 12, paddingRight: 12 },
  panel: { width: 286, borderRadius: 12, overflow: "hidden", backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: "#CBD5E1", elevation: 7 },
  header: { minHeight: 38, paddingHorizontal: 10, flexDirection: "row", alignItems: "center", gap: 8 },
  fixtureLabel: { color: "#7B5A00", fontSize: 10, fontWeight: "900" },
  uiId: { color: "#2563EB", fontSize: 12, fontWeight: "900" },
  state: { fontSize: 10, fontWeight: "900" },
  toggle: { marginLeft: "auto", color: "#64748B", fontSize: 11, fontWeight: "700" },
  body: { borderTopWidth: 1, borderTopColor: "#E2E8F0", padding: 11 },
  headline: { color: "#1E293B", fontSize: 14, lineHeight: 20, fontWeight: "800", marginBottom: 5 },
  fact: { color: "#64748B", fontSize: 12, lineHeight: 18 },
  footer: { marginTop: 8, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  boundary: { color: "#94A3B8", fontSize: 9 },
  link: { color: "#2563EB", fontSize: 11, fontWeight: "800" },
  pressed: { opacity: 0.78 },
});
