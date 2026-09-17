import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

interface Ui03PolicyBlockedNoticeProps {
  onReviewAssessment: () => void;
  onRetry: () => void;
}

export function Ui03PolicyBlockedNotice({
  onReviewAssessment,
  onRetry,
}: Ui03PolicyBlockedNoticeProps) {
  return (
    <View accessibilityRole="alert" style={styles.notice}>
      <Text style={styles.title}>先确认家庭希望怎样使用这份内容</Text>
      <Text style={styles.copy}>
        家庭的隐私与同意设置正在保护这份支持方向。这不是尚未测评，也不是任何人的错误；在权限重新确认前，系统不会继续读取或提交相关内容。
      </Text>
      <View style={styles.actions}>
        <Pressable
          accessibilityLabel="返回测评与同意设置"
          accessibilityRole="button"
          onPress={onReviewAssessment}
          style={({ pressed }) => [
            styles.primaryAction,
            pressed && styles.pressed,
          ]}
        >
          <Text style={styles.primaryActionText}>返回测评与同意设置</Text>
        </Pressable>
        <Pressable
          accessibilityLabel="重新检查查看权限"
          accessibilityRole="button"
          onPress={onRetry}
          style={({ pressed }) => [
            styles.secondaryAction,
            pressed && styles.pressed,
          ]}
        >
          <Text style={styles.secondaryActionText}>重新检查查看权限</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  notice: {
    gap: 12,
    borderWidth: 1,
    borderColor: "#F1C27D",
    borderRadius: 18,
    backgroundColor: "#FFF8E8",
    padding: 18,
  },
  title: {
    color: "#7C4A03",
    fontSize: 17,
    lineHeight: 24,
    fontWeight: "900",
  },
  copy: {
    color: "#76562B",
    fontSize: 14,
    lineHeight: 22,
  },
  actions: {
    gap: 10,
  },
  primaryAction: {
    minHeight: 48,
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 14,
    backgroundColor: "#2563EB",
    paddingHorizontal: 16,
  },
  primaryActionText: {
    color: "#FFFFFF",
    fontSize: 14,
    fontWeight: "800",
  },
  secondaryAction: {
    minHeight: 46,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "#D7A95F",
    borderRadius: 14,
    backgroundColor: "#FFFFFF",
    paddingHorizontal: 16,
  },
  secondaryActionText: {
    color: "#7C4A03",
    fontSize: 14,
    fontWeight: "800",
  },
  pressed: {
    opacity: 0.72,
  },
});
