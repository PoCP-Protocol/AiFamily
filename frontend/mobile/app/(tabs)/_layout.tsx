import { Tabs } from "expo-router";
import { Platform, useWindowDimensions } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { HapticTab } from "@/components/haptic-tab";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { DESKTOP_SHELL_BREAKPOINT } from "@/components/family/responsive-platform-shell";

export default function TabLayout() {
  const colors = useColors();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const desktopWeb = Platform.OS === "web" && width >= DESKTOP_SHELL_BREAKPOINT;
  const bottomPadding = Platform.OS === "web" ? 12 : Math.max(insets.bottom, 8);

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarButton: HapticTab,
        tabBarActiveTintColor: colors.tint,
        tabBarInactiveTintColor: colors.muted,
        tabBarLabelStyle: { fontSize: 11, fontWeight: "600" },
        tabBarStyle: {
          display: desktopWeb ? "none" : "flex",
          height: 58 + bottomPadding,
          paddingTop: 8,
          paddingBottom: bottomPadding,
          backgroundColor: colors.background,
          borderTopColor: colors.border,
          borderTopWidth: 0.5,
        },
      }}
    >
      <Tabs.Screen name="index" options={{ title: "首页", tabBarIcon: ({ color }) => <IconSymbol size={25} name="house.fill" color={color} /> }} />
      <Tabs.Screen name="growth" options={{ title: "计划", tabBarIcon: ({ color }) => <IconSymbol size={25} name="calendar.fill" color={color} /> }} />
      <Tabs.Screen name="discover" options={{ title: "社群", tabBarIcon: ({ color }) => <IconSymbol size={25} name="person.2.fill" color={color} /> }} />
      <Tabs.Screen name="services" options={{ href: null }} />
      <Tabs.Screen name="mine" options={{ title: "我的", tabBarIcon: ({ color }) => <IconSymbol size={25} name="person.crop.circle.fill" color={color} /> }} />
    </Tabs>
  );
}
