import { usePathname } from "expo-router";
import { StyleSheet, View } from "react-native";
import { PrivateAssetActions } from "./private-asset-actions";

const ASSET_SCREENS = {
  "/ui/UI-29": { screenId: "UI-29", title: "成长成果" },
  "/ui/UI-30": { screenId: "UI-30", title: "年度会员服务" },
  "/ui/UI-31": { screenId: "UI-31", title: "我的服务" },
  "/ui/UI-32": { screenId: "UI-32", title: "家庭资产" },
  "/ui/UI-33": { screenId: "UI-33", title: "家庭档案" },
  "/ui/UI-34": { screenId: "UI-34", title: "服务记录" },
} as const;

export function AssetActionsOverlay() {
  const pathname = usePathname();
  const entry = ASSET_SCREENS[pathname as keyof typeof ASSET_SCREENS];
  if (!entry) return null;
  return <View pointerEvents="box-none" style={styles.overlay}><View style={styles.actions}><PrivateAssetActions screenId={entry.screenId} title={entry.title} /></View></View>;
}
const styles = StyleSheet.create({ overlay: { ...StyleSheet.absoluteFillObject, justifyContent: "flex-end", paddingHorizontal: 16, paddingBottom: 18 }, actions: { pointerEvents: "auto" } });
