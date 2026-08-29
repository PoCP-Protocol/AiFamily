import type { PropsWithChildren } from "react";
import { StyleSheet, View } from "react-native";

import { ProjectionStateCard } from "@/components/family/projection-state-card";
import { useColors } from "@/hooks/use-colors";
import { useFamilyMobile } from "@/lib/family/family-state";

export function FamilyMobileHydrationGate({ children }: PropsWithChildren) {
  const colors = useColors();
  const { hydrated } = useFamilyMobile();

  if (!hydrated) {
    return (
      <View style={[styles.page, { backgroundColor: colors.background }]}>
        <ProjectionStateCard
          state="loading"
          title="正在恢复家庭记录"
          detail="正在读取这台设备上保存的行动、草稿和成长进度。"
        />
      </View>
    );
  }

  return children;
}

const styles = StyleSheet.create({
  page: { flex: 1, justifyContent: "center", paddingHorizontal: 24 },
});
