import {
  Pressable,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type ViewStyle,
} from "react-native";

import { IconSymbol } from "@/components/ui/icon-symbol";
import { FamilyTypography } from "@/constants/typography";
import { useColors } from "@/hooks/use-colors";
import type {
  AchievementKey,
  FamilyAchievementProjection,
} from "@/lib/family/achievement-contracts";
import { getAchievementRailViewModel } from "@/lib/family/achievement-view-model";

type AchievementRailProps = {
  projection: FamilyAchievementProjection;
  onOpenAchievement?: (achievementId: string) => void;
  onContinue?: () => void;
  style?: StyleProp<ViewStyle>;
};

const ICON_BY_KEY: Record<
  AchievementKey,
  "checkmark.circle.fill" | "pause.circle.fill" | "person.2.fill" | "star.fill"
> = {
  first_step: "checkmark.circle.fill",
  pause_and_return: "pause.circle.fill",
  service_intent_expressed: "person.2.fill",
  ai_evidence_moment: "star.fill",
};

export function AchievementRail({
  projection,
  onOpenAchievement,
  onContinue,
  style,
}: AchievementRailProps) {
  const colors = useColors();
  const viewModel = getAchievementRailViewModel(projection);

  return (
    <View
      accessibilityRole="summary"
      style={[
        styles.container,
        { backgroundColor: colors.surface, borderColor: colors.border },
        style,
      ]}
    >
      <View style={styles.header}>
        <View style={styles.headerCopy}>
          <Text
            style={[
              FamilyTypography.label,
              styles.eyebrow,
              { color: colors.tint },
            ]}
          >
            {viewModel.eyebrow}
          </Text>
          <Text
            style={[
              FamilyTypography.sectionTitle,
              styles.title,
              { color: colors.text },
            ]}
          >
            {viewModel.title}
          </Text>
          <Text style={[FamilyTypography.supporting, { color: colors.muted }]}>
            {viewModel.subtitle}
          </Text>
        </View>
        {viewModel.availability === "READY" ? (
          <View
            style={[styles.countPill, { backgroundColor: `${colors.tint}14` }]}
          >
            <Text style={[FamilyTypography.label, { color: colors.tint }]}>
              {projection.achievements.length} 个瞬间
            </Text>
          </View>
        ) : null}
      </View>

      {viewModel.visibleAchievements.length > 0 ? (
        <View style={styles.list}>
          {viewModel.visibleAchievements.map((achievement) => {
            const accent =
                achievement.key === "service_intent_expressed"
                  ? colors.success
                  : achievement.key === "pause_and_return"
                    ? colors.warning
                  : colors.tint;
            const content = (
              <>
                <View
                  style={[styles.iconWrap, { backgroundColor: `${accent}16` }]}
                >
                  <IconSymbol
                    name={ICON_BY_KEY[achievement.key]}
                    size={20}
                    color={accent}
                  />
                </View>
                <View style={styles.cardCopy}>
                  <Text
                    style={[
                      FamilyTypography.bodyStrong,
                      styles.cardTitle,
                      { color: colors.text },
                    ]}
                    numberOfLines={1}
                  >
                    {achievement.title}
                  </Text>
                  <Text
                    style={[
                      FamilyTypography.supporting,
                      { color: colors.muted },
                    ]}
                    numberOfLines={2}
                  >
                    {achievement.message}
                  </Text>
                </View>
                {onOpenAchievement ? (
                  <IconSymbol
                    name="chevron.right"
                    size={18}
                    color={colors.muted}
                  />
                ) : null}
              </>
            );

            return onOpenAchievement ? (
              <Pressable
                key={achievement.achievementId}
                accessibilityRole="button"
                accessibilityLabel={`${achievement.title}，${achievement.message}`}
                onPress={() => onOpenAchievement(achievement.achievementId)}
                style={({ pressed }) => [
                  styles.card,
                  { borderColor: colors.border },
                  pressed && styles.pressed,
                ]}
              >
                {content}
              </Pressable>
            ) : (
              <View
                key={achievement.achievementId}
                style={[styles.card, { borderColor: colors.border }]}
              >
                {content}
              </View>
            );
          })}
        </View>
      ) : null}

      <View style={[styles.prompt, { backgroundColor: `${colors.primary}12` }]}>
        <View style={styles.promptCopy}>
          <Text style={[FamilyTypography.label, { color: colors.primary }]}>
            下一步
          </Text>
          <Text style={[FamilyTypography.supporting, { color: colors.text }]}>
            {viewModel.prompt}
          </Text>
        </View>
        {onContinue ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="继续今天的一步"
            onPress={onContinue}
            style={({ pressed }) => [
              styles.continueButton,
              { backgroundColor: colors.primary },
              pressed && styles.pressed,
            ]}
          >
            <Text style={[FamilyTypography.label, styles.continueText]}>
              继续
            </Text>
            <IconSymbol name="chevron.right" size={16} color="#FFFFFF" />
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { borderWidth: 1, borderRadius: 24, padding: 16, gap: 14 },
  header: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  headerCopy: { flex: 1, gap: 4 },
  eyebrow: { letterSpacing: 1.1 },
  title: { marginTop: 1 },
  countPill: { borderRadius: 999, paddingHorizontal: 10, paddingVertical: 6 },
  list: { gap: 9 },
  card: {
    minHeight: 72,
    borderWidth: 1,
    borderRadius: 17,
    paddingHorizontal: 11,
    paddingVertical: 10,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  iconWrap: {
    width: 38,
    height: 38,
    borderRadius: 13,
    alignItems: "center",
    justifyContent: "center",
  },
  cardCopy: { flex: 1, gap: 1 },
  cardTitle: { lineHeight: 21 },
  prompt: {
    borderRadius: 17,
    paddingHorizontal: 12,
    paddingVertical: 11,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  promptCopy: { flex: 1, gap: 2 },
  continueButton: {
    minHeight: 44,
    borderRadius: 13,
    paddingHorizontal: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 3,
  },
  continueText: { color: "#FFFFFF" },
  pressed: { opacity: 0.75, transform: [{ scale: 0.985 }] },
});
