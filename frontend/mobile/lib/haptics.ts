import * as Haptics from "expo-haptics";
import { Platform } from "react-native";

export const haptic = {
  light() {
    if (Platform.OS !== "web") void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
  },
  success() {
    if (Platform.OS !== "web") void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
  },
  selection() {
    if (Platform.OS !== "web") void Haptics.selectionAsync();
  },
};
