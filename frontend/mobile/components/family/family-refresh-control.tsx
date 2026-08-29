import { useCallback, useMemo, useState, type PropsWithChildren } from "react";
import { FlatList, StyleSheet, type FlatListProps, Platform, RefreshControl } from "react-native";

import { useColors } from "@/hooks/use-colors";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { useFamilyMobile } from "@/lib/family/family-state";
import { createFamilyRefreshRunner } from "@/lib/family/pull-to-refresh";

export function FamilyRefreshControl({ children }: PropsWithChildren) {
  const colors = useColors();
  const session = useFamilyApiSession();
  const { reloadLocalState } = useFamilyMobile();
  const [refreshing, setRefreshing] = useState(false);
  const runRefresh = useMemo(
    () => createFamilyRefreshRunner({ refreshRemote: session.refresh, reloadLocal: reloadLocalState }),
    [reloadLocalState, session.refresh],
  );

  const handleRefresh = useCallback(async () => {
    if (refreshing) return;
    setRefreshing(true);
    try {
      await runRefresh();
    } finally {
      setRefreshing(false);
    }
  }, [refreshing, runRefresh]);

  if (Platform.OS === "web") return children ?? null;

  return (
    <RefreshControl
      refreshing={refreshing}
      onRefresh={() => { void handleRefresh(); }}
      tintColor={colors.tint}
      colors={[colors.tint, colors.success, colors.warning]}
      progressBackgroundColor={colors.surface}
      title={refreshing ? "正在同步家庭记录" : undefined}
      titleColor={colors.muted}
    />
  );
}

export function FamilyFlatList<ItemT>(props: FlatListProps<ItemT>) {
  const colors = useColors();

  return (
    <FlatList
      {...props}
      style={[styles.list, { backgroundColor: colors.background }, props.style]}
      refreshControl={props.refreshControl ?? <FamilyRefreshControl />}
    />
  );
}

const styles = StyleSheet.create({
  list: { flex: 1 },
});
