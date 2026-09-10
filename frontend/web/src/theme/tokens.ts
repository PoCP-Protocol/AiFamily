/**
 * Web-side mirror of the mobile design tokens.
 *
 * Source of truth is `frontend/mobile/theme.config.js` (colors) and
 * `frontend/mobile/constants/typography.ts` (typography). Mobile and web are
 * two independent npm projects with no shared workspace, so these values are
 * hand-copied rather than imported — `theme-parity.test.ts` in this same
 * directory asserts them against the mobile values so a change on one side
 * that forgets the other side fails CI instead of silently drifting.
 *
 * If you change a value here, change frontend/mobile's source file too.
 */

export type ColorScheme = "light" | "dark";

export const themeColors = {
  primary: { light: "#F28C45", dark: "#FFB178" },
  trust: { light: "#0078D4", dark: "#45A9F0" },
  growth: { light: "#16866D", dark: "#46C7A8" },
  background: { light: "#FFF9F3", dark: "#14110F" },
  surface: { light: "#FFFFFF", dark: "#241E1A" },
  foreground: { light: "#10213E", dark: "#F8F4EF" },
  muted: { light: "#64748B", dark: "#B8AEA5" },
  border: { light: "#E8DED3", dark: "#40362F" },
  success: { light: "#16866D", dark: "#46C7A8" },
  warning: { light: "#B87500", dark: "#F6C453" },
  error: { light: "#D9554F", dark: "#F58A82" },
} as const;

export type ColorToken = keyof typeof themeColors;

export function paletteFor(scheme: ColorScheme): Record<ColorToken, string> {
  const palette = {} as Record<ColorToken, string>;
  (Object.keys(themeColors) as ColorToken[]).forEach((token) => {
    palette[token] = themeColors[token][scheme];
  });
  return palette;
}

export const fontFamily =
  '"PingFang SC", "Microsoft YaHei", "Noto Sans SC", system-ui, sans-serif';

export const typography = {
  hero: { fontSize: 28, lineHeight: 38, fontWeight: 800, letterSpacing: -0.4 },
  screenTitle: { fontSize: 20, lineHeight: 28, fontWeight: 800 },
  sectionTitle: { fontSize: 17, lineHeight: 24, fontWeight: 700 },
  body: { fontSize: 15, lineHeight: 24, fontWeight: 400 },
  bodyStrong: { fontSize: 15, lineHeight: 24, fontWeight: 600 },
  supporting: { fontSize: 13, lineHeight: 20, fontWeight: 400 },
  label: { fontSize: 12, lineHeight: 18, fontWeight: 600 },
  button: { fontSize: 16, lineHeight: 22, fontWeight: 700 },
  metric: { fontSize: 28, lineHeight: 34, fontWeight: 800 },
} as const;

export const MIN_TOUCH_TARGET = 44;
