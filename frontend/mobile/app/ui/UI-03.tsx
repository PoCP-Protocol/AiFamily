import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { familyApi } from "@/lib/family/family-api-client";
import { useFamilyApiSession } from "@/lib/family/family-api-session";

type AssessmentResult = {
  result_id: string;
  subject: { person_id: string; display_name: string };
  focus_ref: string;
  family_need_ref: string;
  title: string;
  explanation: {
    headline: string;
    summary: string;
    observations: { item_ref: string; response_value: string | boolean; kind: string }[];
    hypothesis: string;
    recommendations: { text: string; source: string; status: "DRAFT" }[];
  };
  evidence_lineage: {
    source_refs: string[];
    tool_ref: string;
    tool_version: number;
    submitted_at: string | null;
  };
  ai: {
    generator: string;
    model: string | null;
    model_version: string | null;
    prompt_version: string | null;
    context_snapshot_ref: string | null;
    provenance_refs: string[];
    model_gateway_status: "NOT_INVOKED" | "DRAFT" | "BLOCKED";
    may_mutate_business_state: false;
  };
  boundary: "FAMILY_PERSPECTIVE_NOT_SCORE_OR_DIAGNOSIS";
  draft_metadata: { boundary_labels: string[]; review_required: boolean };
};

type AssessmentResultProjection = {
  projection_version: "ASSESSMENT_RESULT_V1";
  tenant_id: string;
  family_id: string;
  status: "READY" | "NO_RESULT" | "CONSENT_REQUIRED" | "POLICY_BLOCKED";
  result: AssessmentResult | null;
};

export default function GrowthExplanationScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const [remote, setRemote] = useState<AssessmentResultProjection | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [retryNonce, setRetryNonce] = useState(0);

  useEffect(() => {
    if (session.status !== "connected" || !session.token || !session.selectedFamily) {
      setState("idle");
      return;
    }
    let active = true;
    setState("loading");
    void familyApi
      .getLatestAssessmentResult<AssessmentResultProjection>(session.token, session.selectedFamily.family_id)
      .then((result) => {
        if (active) {
          setRemote(result);
          setState("ready");
        }
      })
      .catch(() => {
        if (active) setState("error");
      });
    return () => {
      active = false;
    };
  }, [retryNonce, session.selectedFamily, session.status, session.token]);

  if (state === "loading") {
    return (
      <ScreenContainer edges={["left", "right", "bottom"]}>
        <Stack.Screen options={{ headerShown: true, title: "家庭支持解释", headerBackTitle: "退出" }} />
        <View style={styles.emptyPage}>
          <ActivityIndicator color={colors.tint} />
          <Text style={[styles.emptyTitle, { color: colors.text }]}>正在整理这次家庭测评</Text>
          <Text style={[styles.emptyText, { color: colors.muted }]}>只根据本次已提交回答整理支持方向，不生成家庭分数或诊断。</Text>
        </View>
      </ScreenContainer>
    );
  }

  const result = remote?.result;
  const unavailableText = remote?.status === "CONSENT_REQUIRED"
    ? "测评授权已撤回，系统已停止展示这次结果。重新确认授权后可以重新开始。"
    : remote?.status === "POLICY_BLOCKED"
      ? "当前家庭策略尚未开放测评结果。"
      : "还没有已提交的家庭测评，请先完成最小题集。";

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: true, title: "家庭支持解释", headerBackTitle: "退出" }} />
      <ScrollView contentContainerStyle={styles.content}>
        {state === "error" ? (
          <View style={styles.notice}>
            <Text style={styles.noticeTitle}>暂时无法读取测评结果</Text>
            <Text style={styles.noticeText}>请稍后重试；已有提交不会因为读取失败而重复创建。</Text>
            <Pressable onPress={() => setRetryNonce((value) => value + 1)} style={styles.retryButton}>
              <Text style={styles.retryText}>重新读取</Text>
            </Pressable>
          </View>
        ) : null}
        {!result ? (
          <View style={styles.emptyPage}>
            <Text style={[styles.emptyTitle, { color: colors.text }]}>{unavailableText}</Text>
            <Text style={[styles.emptyText, { color: colors.muted }]}>这是家庭视角下的支持整理，不是对孩子的评分、排名或诊断。</Text>
          </View>
        ) : (
          <>
            <View style={styles.hero}>
              <View style={styles.heroIcon}>
                <IconSymbol name="checkmark.circle.fill" size={26} color="#1B7CF2" />
              </View>
              <View style={styles.heroCopy}>
                <Text style={styles.badge}>家庭范围 · 可回读结果</Text>
                <Text style={styles.heroTitle}>{result.explanation.headline}</Text>
                <Text style={styles.heroText}>{result.subject.display_name}的这次家庭支持方向：{result.title}</Text>
              </View>
            </View>

            <View style={styles.card}>
              <Text style={styles.sectionLabel}>为什么这样整理</Text>
              <Text style={styles.cardTitle}>{result.title}</Text>
              <Text style={styles.cardText}>{result.explanation.summary}</Text>
              {result.explanation.observations.length > 0 ? (
                <View style={styles.observations}>
                  {result.explanation.observations.map((observation) => (
                    <View key={observation.item_ref} style={styles.observationRow}>
                      <View style={styles.dot} />
                      <Text style={styles.cardText}>{String(observation.response_value)}</Text>
                    </View>
                  ))}
                </View>
              ) : null}
            </View>

            <View style={styles.directionCard}>
              <Text style={styles.sectionLabel}>可以先尝试</Text>
              {result.explanation.recommendations.map((recommendation) => (
                <Text key={recommendation.text} style={styles.directionText}>• {recommendation.text}</Text>
              ))}
            </View>

            <View style={styles.provenanceCard}>
              <Text style={styles.sectionLabel}>本次结果依据</Text>
              <Text style={styles.provenanceText}>测评版本 v{result.evidence_lineage.tool_version} · {result.evidence_lineage.source_refs.length} 条已提交证据引用</Text>
              <Text style={styles.provenanceText}>解释状态：{result.ai.model_gateway_status === "NOT_INVOKED" ? "确定性 sandbox 基线，未调用模型" : result.ai.model_gateway_status}</Text>
              <Text style={styles.provenanceText}>AI 不能修改业务状态：{result.ai.may_mutate_business_state ? "否" : "是"}</Text>
            </View>

            <Text style={styles.boundaryText}>{result.explanation.hypothesis} {result.boundary.replaceAll("_", " ")}</Text>
          </>
        )}

        <Pressable onPress={() => router.replace("/ui/UI-02" as Href)} style={({ pressed }) => [styles.primaryButton, { backgroundColor: colors.tint }, pressed && styles.pressed]}>
          <Text style={styles.primaryButtonText}>重新开始测评</Text>
        </Pressable>
        <Pressable onPress={() => router.back()} style={({ pressed }) => [styles.exitButton, pressed && styles.pressed]}>
          <Text style={[styles.exitText, { color: colors.muted }]}>退出</Text>
        </Pressable>
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  content: { flexGrow: 1, padding: 16, gap: 14 },
  emptyPage: { flex: 1, padding: 24, justifyContent: "center", gap: 14 },
  emptyTitle: { fontSize: 25, lineHeight: 33, fontWeight: "800" },
  emptyText: { fontSize: 14, lineHeight: 22 },
  notice: { borderRadius: 16, backgroundColor: "#FFF6DF", borderWidth: 1, borderColor: "#F8DE94", padding: 14, gap: 4 },
  noticeTitle: { color: "#8A5A00", fontSize: 14, lineHeight: 20, fontWeight: "900" },
  noticeText: { color: "#6F5A36", fontSize: 12, lineHeight: 18, fontWeight: "700" },
  retryButton: { alignSelf: "flex-start", minHeight: 32, justifyContent: "center" },
  retryText: { color: "#2563EB", fontSize: 12, lineHeight: 18, fontWeight: "900", textDecorationLine: "underline" },
  hero: { borderRadius: 20, backgroundColor: "#E8F2FF", padding: 16, gap: 12, flexDirection: "row", alignItems: "flex-start" },
  heroIcon: { width: 40, height: 40, borderRadius: 13, backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center" },
  heroCopy: { flex: 1, gap: 5 },
  badge: { color: "#2563EB", fontSize: 11, lineHeight: 15, fontWeight: "900" },
  heroTitle: { color: "#09295A", fontSize: 19, lineHeight: 26, fontWeight: "900" },
  heroText: { color: "#5B7091", fontSize: 13, lineHeight: 20, fontWeight: "700" },
  card: { borderRadius: 16, backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: "#D9E8FA", padding: 15, gap: 8 },
  sectionLabel: { color: "#5B7091", fontSize: 12, lineHeight: 17, fontWeight: "900" },
  cardTitle: { color: "#09295A", fontSize: 18, lineHeight: 24, fontWeight: "900" },
  cardText: { color: "#344A68", fontSize: 14, lineHeight: 21 },
  observations: { gap: 6, marginTop: 2 },
  observationRow: { flexDirection: "row", alignItems: "flex-start", gap: 8 },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: "#16866D", marginTop: 8 },
  directionCard: { borderRadius: 16, backgroundColor: "#F7FBF8", borderWidth: 1, borderColor: "#D8EBDD", padding: 15, gap: 8 },
  directionText: { color: "#214B3D", fontSize: 14, lineHeight: 21, fontWeight: "700" },
  provenanceCard: { borderRadius: 16, backgroundColor: "#F5F9FF", borderWidth: 1, borderColor: "#D9E8FA", padding: 15, gap: 5 },
  provenanceText: { color: "#5B7091", fontSize: 12, lineHeight: 18, fontWeight: "700" },
  boundaryText: { color: "#5B7091", fontSize: 11, lineHeight: 18, textAlign: "center" },
  primaryButton: { minHeight: 50, borderRadius: 25, alignItems: "center", justifyContent: "center" },
  primaryButtonText: { color: "#FFFFFF", fontSize: 16, lineHeight: 22, fontWeight: "900" },
  exitButton: { minHeight: 42, alignItems: "center", justifyContent: "center" },
  exitText: { fontSize: 13, lineHeight: 20, fontWeight: "800", textDecorationLine: "underline" },
  pressed: { opacity: 0.82 },
});
