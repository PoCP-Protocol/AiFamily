import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { projectionStateLabel, type ProjectionViewState } from "@/lib/family/projection-state";

interface ProjectionStateCardProps {
  state: ProjectionViewState;
  title?: string;
  detail?: string;
  onRetry?: () => void;
  retryLabel?: string;
  compact?: boolean;
}

export function ProjectionStateCard({ state, title, detail, onRetry, retryLabel = "再试一次", compact = false }: ProjectionStateCardProps) {
  const colors = useColors();
  if (state === "hidden") return null;

  const busy = state === "loading" || state === "refreshing";
  const warning = state === "error" || state === "fallback";
  const accent = warning ? colors.warning : state === "empty" ? colors.muted : colors.tint;
  const defaultDetail = state === "loading"
    ? "正在从家庭空间读取最新内容，请稍等。"
    : state === "refreshing"
      ? "先显示已经保存的内容，最新记录会在连接后更新。"
      : state === "error"
        ? "你可以稍后重试；尚未同步的内容不会丢失。"
        : state === "fallback"
          ? "远端记录暂时不可用，当前显示本机草稿或已准备的体验内容。"
          : "完成一次相关行动或保存一份草稿后，这里会出现可回看的内容。";

  return (
    <View accessibilityRole="summary" style={[styles.card, compact && styles.compact, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      <View style={[styles.icon, compact && styles.compactIcon, { backgroundColor: `${accent}16` }]}>
        {busy ? <ActivityIndicator size="small" color={accent} /> : <IconSymbol name={state === "error" ? "shield.fill" : state === "empty" ? "book.fill" : "clock.fill"} size={compact ? 18 : 21} color={accent} />}
      </View>
      <View style={styles.copy}>
        <Text style={[styles.title, compact && styles.compactTitle, { color: colors.text }]}>{title ?? projectionStateLabel(state)}</Text>
        <Text style={[styles.detail, compact && styles.compactDetail, { color: colors.muted }]}>{detail ?? defaultDetail}</Text>
      </View>
      {!busy && onRetry ? (
        <Pressable accessibilityRole="button" onPress={onRetry} style={({ pressed }) => [styles.button, { borderColor: colors.border }, pressed && styles.pressed]}>
          <Text style={[styles.buttonText, { color: colors.tint }]}>{retryLabel}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { minHeight: 82, borderWidth: 1, borderRadius: 18, paddingHorizontal: 13, paddingVertical: 12, flexDirection: "row", alignItems: "center", gap: 10 },
  compact: { minHeight: 66, borderRadius: 16, paddingVertical: 9 },
  icon: { width: 42, height: 42, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  compactIcon: { width: 34, height: 34, borderRadius: 12 },
  copy: { flex: 1, gap: 2 },
  title: { fontSize: 13, lineHeight: 18, fontWeight: "900" },
  compactTitle: { fontSize: 12, lineHeight: 17 },
  detail: { fontSize: 11, lineHeight: 17 },
  compactDetail: { fontSize: 10, lineHeight: 15 },
  button: { minWidth: 66, minHeight: 38, borderWidth: 1, borderRadius: 13, alignItems: "center", justifyContent: "center", paddingHorizontal: 9 },
  buttonText: { fontSize: 11, lineHeight: 16, fontWeight: "900" },
  pressed: { opacity: 0.72, transform: [{ scale: 0.98 }] },
});
