// Fallback for using MaterialIcons on Android and web.

import MaterialIcons from "@expo/vector-icons/MaterialIcons";
import { SymbolWeight } from "expo-symbols";
import { ComponentProps } from "react";
import { OpaqueColorValue, type StyleProp, type TextStyle } from "react-native";

type MaterialIconName = ComponentProps<typeof MaterialIcons>["name"];

/**
 * Add your SF Symbols to Material Icons mappings here.
 * - see Material Icons in the [Icons Directory](https://icons.expo.fyi).
 * - see SF Symbols in the [SF Symbols](https://developer.apple.com/sf-symbols/) app.
 */
const MAPPING = {
  "house.fill": "home",
  "paperplane.fill": "send",
  "chevron.left.forwardslash.chevron.right": "code",
  "chevron.left": "chevron-left",
  "chevron.right": "chevron-right",
  "chevron.down": "expand-more",
  "chart.bar.fill": "insights",
  "safari.fill": "explore",
  "person.2.fill": "groups",
  "person.crop.circle.fill": "account-circle",
  "checkmark.circle.fill": "check-circle",
  "checkmark.seal.fill": "verified",
  "pause.circle.fill": "pause-circle-filled",
  "lock.fill": "lock",
  "gift.fill": "card-giftcard",
  "cart.fill": "shopping-cart",
  "star.fill": "stars",
  "book.fill": "menu-book",
  "ticket.fill": "confirmation-number",
  "wallet.fill": "account-balance-wallet",
  "crown.fill": "workspace-premium",
  "calendar.fill": "calendar-month",
  "headphones.fill": "support-agent",
  "magnifyingglass": "search",
  "video.fill": "videocam",
  "phone.fill": "phone",
  "message.fill": "chat-bubble",
  "mappin.circle.fill": "location-on",
  "clock.fill": "schedule",
  "arrow.up.right.square": "open-in-new",
  "doc.text.fill": "description",
  "square.and.arrow.up": "ios-share",
  "square.and.pencil": "edit-note",
  "bookmark.fill": "bookmark",
  "eye.fill": "visibility",
  "shield.fill": "shield",
  "photo.fill": "photo-library",
  "heart.fill": "favorite",
  "bell.fill": "notifications-none",
  "ellipsis": "more-horiz",
} as const satisfies Record<string, MaterialIconName>;

type IconSymbolName = keyof typeof MAPPING;

/**
 * An icon component that uses native SF Symbols on iOS, and Material Icons on Android and web.
 * This ensures a consistent look across platforms, and optimal resource usage.
 * Icon `name`s are based on SF Symbols and require manual mapping to Material Icons.
 */
export function IconSymbol({
  name,
  size = 24,
  color,
  style,
}: {
  name: IconSymbolName;
  size?: number;
  color: string | OpaqueColorValue;
  style?: StyleProp<TextStyle>;
  weight?: SymbolWeight;
}) {
  return <MaterialIcons color={color} size={size} name={MAPPING[name]} style={style} />;
}
