import type { ReactNode } from "react";
import { Platform, StyleSheet, View, useWindowDimensions } from "react-native";

import { useColors } from "@/hooks/use-colors";

// Mobile tab parity metadata only. This is not rendered as a desktop rail.
export const FAMILY_PRIMARY_NAV = [
  { label: "今天", route: "/" },
  { label: "成长", route: "/growth" },
  { label: "发现", route: "/discover" },
  { label: "服务", route: "/services" },
  { label: "我的", route: "/mine" },
] as const;

export const DESKTOP_SHELL_BREAKPOINT = 760;
export const WIDE_DESKTOP_BREAKPOINT = 1240;
const PHONE_WIDTH = 440;

/** The browser is only a preview surface for the phone product. */
export function ResponsivePlatformShell({ children }: { children: ReactNode }) {
  const colors = useColors();
  const { width } = useWindowDimensions();

  if (Platform.OS !== "web" || width < DESKTOP_SHELL_BREAKPOINT) {
    return <>{children}</>;
  }

  return (
    <View style={[styles.previewCanvas, { backgroundColor: "#EEE9E2" }]}>
      <View
        style={[
          styles.phoneViewport,
          { borderColor: colors.border, backgroundColor: colors.background },
        ]}
      >
        {children}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  previewCanvas: {
    flex: 1,
    minHeight: "100vh" as never,
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 20,
  },
  phoneViewport: {
    width: PHONE_WIDTH,
    minHeight: 720,
    height: "calc(100vh - 40px)" as never,
    maxHeight: "calc(100vh - 40px)" as never,
    overflow: "hidden",
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 32,
    shadowColor: "#5B5146",
    shadowOpacity: 0.12,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 14 },
    elevation: 8,
  },
});
