import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { useSyncExternalStore } from "react";
import { usePathname } from "expo-router";

import { useColors } from "@/hooks/use-colors";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { getFamilyApiRequestSnapshot, subscribeFamilyApiRequestSnapshot } from "@/lib/family/family-api-client";
import { projectionCopyForUi } from "@/lib/family/projection-state";

export function DataSourceBanner() {
  const colors = useColors();
  const pathname = usePathname();
  const { configured, status, selectedFamily, error, connectDevSession, refresh } = useFamilyApiSession();
  const request = useSyncExternalStore(subscribeFamilyApiRequestSnapshot, getFamilyApiRequestSnapshot, getFamilyApiRequestSnapshot);
  const connected = status === "connected" && selectedFamily;
  const loadingProjection = request.activeCount > 0;
  const projectionError = !loadingProjection && Boolean(request.lastError);
  const projectionEmpty = connected && !loadingProjection && !projectionError && request.lastResult === "empty";
  const uiId = pathname.match(/UI-\d{2}/)?.[0] ?? null;
  const copy = projectionCopyForUi(uiId);

  return (
    <View style={[styles.banner, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      {loadingProjection ? <ActivityIndicator size="small" color={colors.tint} /> : <View style={[styles.dot, { backgroundColor: connected && !projectionError ? colors.success : colors.warning }]} />}
      <View style={styles.copy}>
        <Text style={[styles.title, { color: colors.text }]}>{loadingProjection ? copy.loading : projectionError ? "最新记录暂时没有连上" : projectionEmpty ? copy.emptyTitle : connected ? "家庭成长记录已同步" : "本机家庭体验已准备"}</Text>
        <Text style={[styles.detail, { color: colors.muted }]}> 
          {loadingProjection
            ? "先显示已经保存的内容，连接完成后会自动更新。"
            : projectionError
              ? "当前页面仍可查看本机内容；稍后可再次同步。"
              : projectionEmpty
                ? copy.emptyDetail
              : connected
            ? "成长记录、方案意向和权益信息来自同一家庭空间。"
            : error ? "家庭记录暂时无法同步；本机内容仍可继续使用。" : configured ? "连接家庭账户后，可以同步成长记录和权益。" : "你可以先浏览和保存本机草稿，之后再同步家庭记录。"}
        </Text>
      </View>
      {configured && ((!connected && !loadingProjection) || projectionError) ? (
        <Pressable
          accessibilityRole="button"
          onPress={() => { void (connected ? refresh() : status === "error" ? refresh() : connectDevSession()); }}
          style={({ pressed }) => [styles.button, { borderColor: colors.border }, pressed && styles.pressed]}
        >
          <Text style={[styles.buttonText, { color: colors.tint }]}>{status === "loading" || loadingProjection ? "同步中" : projectionError ? "重试" : "同步"}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  banner: { minHeight: 74, borderWidth: 1, borderRadius: 18, paddingHorizontal: 14, paddingVertical: 12, flexDirection: "row", alignItems: "center", gap: 11 },
  dot: { width: 9, height: 9, borderRadius: 5 },
  copy: { flex: 1, gap: 2 },
  title: { fontSize: 14, lineHeight: 19, fontWeight: "800" },
  detail: { fontSize: 12, lineHeight: 17 },
  button: { minWidth: 60, minHeight: 40, borderWidth: 1, borderRadius: 13, alignItems: "center", justifyContent: "center", paddingHorizontal: 10 },
  buttonText: { fontSize: 13, lineHeight: 18, fontWeight: "800" },
  pressed: { opacity: 0.7 },
});
