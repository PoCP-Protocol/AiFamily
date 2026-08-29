import type { Href } from "expo-router";
import { router } from "expo-router";
import { FlatList, Pressable, StyleSheet, Text, View } from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { getScreensForTab, type FamilyTab } from "@/lib/family/ui-registry";

interface FamilyScreenListProps {
  tab: FamilyTab;
  eyebrow: string;
  title: string;
  description: string;
}

export function FamilyScreenList({ tab, eyebrow, title, description }: FamilyScreenListProps) {
  const colors = useColors();
  const screens = getScreensForTab(tab);

  return (
    <ScreenContainer>
      <FlatList
        data={screens}
        keyExtractor={(item) => item.id}
        contentContainerStyle={styles.content}
        ListHeaderComponent={
          <View style={styles.header}>
            <Text style={[styles.eyebrow, { color: colors.tint }]}>{eyebrow}</Text>
            <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
            <Text style={[styles.description, { color: colors.muted }]}>{description}</Text>
          </View>
        }
        renderItem={({ item }) => (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={`${item.title}，${item.subtitle}`}
            onPress={() => router.push(`/ui/${item.id}` as Href)}
            style={({ pressed }) => [
              styles.row,
              { backgroundColor: colors.surface, borderColor: colors.border },
              pressed && styles.pressed,
            ]}
          >
            <View style={[styles.idBadge, { backgroundColor: colors.background }]}>
              <Text style={[styles.idText, { color: colors.tint }]}>{item.id}</Text>
            </View>
            <View style={styles.rowCopy}>
              <Text style={[styles.rowTitle, { color: colors.text }]}>{item.title}</Text>
              <Text style={[styles.rowSubtitle, { color: colors.muted }]} numberOfLines={2}>
                {item.subtitle}
              </Text>
              <Text style={[styles.loop, { color: colors.success }]}>{item.loop}循环</Text>
            </View>
            <IconSymbol name="chevron.right" size={20} color={colors.muted} />
          </Pressable>
        )}
      />
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 20, paddingTop: 18, paddingBottom: 28, gap: 12 },
  header: { gap: 8, marginBottom: 12 },
  eyebrow: { fontSize: 13, lineHeight: 18, fontWeight: "700", letterSpacing: 1 },
  title: { fontSize: 30, lineHeight: 38, fontWeight: "800" },
  description: { fontSize: 16, lineHeight: 24, maxWidth: 520 },
  row: { minHeight: 104, borderWidth: 1, borderRadius: 20, padding: 16, flexDirection: "row", alignItems: "center", gap: 14 },
  pressed: { opacity: 0.72, transform: [{ scale: 0.99 }] },
  idBadge: { width: 52, height: 52, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  idText: { fontSize: 12, lineHeight: 16, fontWeight: "800" },
  rowCopy: { flex: 1, gap: 4 },
  rowTitle: { fontSize: 17, lineHeight: 23, fontWeight: "700" },
  rowSubtitle: { fontSize: 14, lineHeight: 20 },
  loop: { fontSize: 12, lineHeight: 16, fontWeight: "700" },
});
