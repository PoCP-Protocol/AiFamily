import { Platform } from "react-native";
import type { TextStyle } from "react-native";

export const FamilyFontFamily = Platform.select({
  ios: "PingFang SC",
  android: "sans-serif",
  web: '"PingFang SC", "Microsoft YaHei", "Noto Sans SC", system-ui, sans-serif',
  default: "system-ui",
});

export const FamilyTypography = {
  hero: {
    fontFamily: FamilyFontFamily,
    fontSize: 28,
    lineHeight: 38,
    fontWeight: "800",
    letterSpacing: -0.4,
  },
  screenTitle: {
    fontFamily: FamilyFontFamily,
    fontSize: 20,
    lineHeight: 28,
    fontWeight: "800",
  },
  sectionTitle: {
    fontFamily: FamilyFontFamily,
    fontSize: 17,
    lineHeight: 24,
    fontWeight: "700",
  },
  body: {
    fontFamily: FamilyFontFamily,
    fontSize: 15,
    lineHeight: 24,
    fontWeight: "400",
  },
  bodyStrong: {
    fontFamily: FamilyFontFamily,
    fontSize: 15,
    lineHeight: 24,
    fontWeight: "600",
  },
  supporting: {
    fontFamily: FamilyFontFamily,
    fontSize: 13,
    lineHeight: 20,
    fontWeight: "400",
  },
  label: {
    fontFamily: FamilyFontFamily,
    fontSize: 12,
    lineHeight: 18,
    fontWeight: "600",
  },
  button: {
    fontFamily: FamilyFontFamily,
    fontSize: 16,
    lineHeight: 22,
    fontWeight: "700",
  },
  metric: {
    fontFamily: FamilyFontFamily,
    fontSize: 28,
    lineHeight: 34,
    fontWeight: "800",
    fontVariant: ["tabular-nums"],
  },
} satisfies Record<string, TextStyle>;

export const MIN_TOUCH_TARGET = 44;
