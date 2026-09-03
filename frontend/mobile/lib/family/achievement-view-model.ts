import type {
  AchievementAvailability,
  FamilyAchievement,
  FamilyAchievementProjection,
} from "./achievement-contracts";

export type AchievementRailViewModel = {
  eyebrow: string;
  title: string;
  subtitle: string;
  prompt: string;
  availability: AchievementAvailability;
  visibleAchievements: FamilyAchievement[];
};

/**
 * Keep copy and selection rules outside the component so screens can reuse the
 * same emotional rhythm without coupling themselves to a rendering library.
 */
export function getAchievementRailViewModel(
  projection: FamilyAchievementProjection,
): AchievementRailViewModel {
  const visibleAchievements = projection.achievements.slice(0, 3);

  if (projection.availability === "UNAVAILABLE") {
    return {
      eyebrow: "FAMILY MOMENTS",
      title: "先把重要的一步留住",
      subtitle: "成就记录暂时不可用，已完成的行动不会因此丢失。",
      prompt:
        projection.nextPrompt?.trim() || "连接恢复后，我们会继续整理家庭瞬间。",
      availability: "UNAVAILABLE",
      visibleAchievements,
    };
  }

  if (visibleAchievements.length === 0) {
    return {
      eyebrow: "FAMILY MOMENTS",
      title: "把每一步，变成我们的成就",
      subtitle: "从一次自己选择的小行动开始，留下第一枚家庭成就。",
      prompt:
        projection.nextPrompt?.trim() || "选一个今天愿意一起完成的小行动。",
      availability: "EMPTY",
      visibleAchievements,
    };
  }

  return {
    eyebrow: "FAMILY MOMENTS",
    title: "把每一步，变成我们的成就",
    subtitle: `已经记录 ${projection.achievements.length} 个属于家庭的真实瞬间。`,
    prompt: projection.nextPrompt?.trim() || "准备好后，继续今天的一小步。",
    availability: "READY",
    visibleAchievements,
  };
}
