import type { Href } from "expo-router";
import { Stack, router } from "expo-router";
import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import {
  AssessmentApiContractError,
  type Ui03GrowthHypothesisProjection,
} from "@/lib/family/assessment-api-contracts";
import { familyApi, FamilyApiError } from "@/lib/family/family-api-client";
import { useFamilyApiSession } from "@/lib/family/family-api-session";
import { ui03FlowContextForFamily } from "@/lib/family/family-state-core";
import { useFamilyMobile } from "@/lib/family/family-state";
import {
  isRetryableUi03FlowError,
  Ui03FlowStaleError,
  Ui03HumanTaskFlow,
} from "@/lib/family/ui03-human-task-flow";

type RemoteState =
  | "idle"
  | "loading"
  | "ready"
  | "empty"
  | "denied"
  | "contract_blocked"
  | "error";
type DecisionState =
  | "idle"
  | "saving"
  | "retryable"
  | "contract_blocked"
  | "success"
  | "rejected";

export default function GrowthExplanationScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const { ui03FlowContext, setUi03FlowContext } = useFamilyMobile();
  const [remote, setRemote] = useState<Ui03GrowthHypothesisProjection | null>(
    null,
  );
  const [remoteState, setRemoteState] = useState<RemoteState>("idle");
  const [decisionState, setDecisionState] = useState<DecisionState>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [rejectionReason, setRejectionReason] = useState("");
  const flowRef = useRef<Ui03HumanTaskFlow | null>(null);
  flowRef.current ??= new Ui03HumanTaskFlow(familyApi);

  const familyId = session.selectedFamily?.family_id ?? null;
  const hypothesis = remote?.hypothesis ?? null;
  const humanTaskId = hypothesis?.scorecard.human_task_ref ?? null;
  const activeContext = ui03FlowContextForFamily(ui03FlowContext, familyId);
  const confirmed = Boolean(
    activeContext &&
    activeContext.hypothesisRef === hypothesis?.hypothesis_ref &&
    activeContext.humanTaskId === humanTaskId,
  );

  useEffect(() => {
    const flow = flowRef.current;
    flow?.invalidate();
    setRemote(null);
    setDecisionState("idle");
    setMessage(null);
    setRejectionReason("");
    if (session.status !== "connected" || !session.token || !familyId) {
      setRemoteState("idle");
      return () => flow?.invalidate();
    }

    const token = session.token;
    let active = true;
    setRemoteState("loading");
    void familyApi
      .getGrowthHypothesis(token, familyId)
      .then((result) => {
        if (!active) return;
        setRemote(result);
        if (result.availability === "POLICY_BLOCKED") {
          setRemoteState("denied");
          return;
        }
        if (result.availability === "NO_SUBMITTED_ASSESSMENT") {
          setRemoteState("empty");
          return;
        }
        flow?.bind(result);
        setRemoteState("ready");
      })
      .catch((error: unknown) => {
        if (!active) return;
        if (
          error instanceof AssessmentApiContractError ||
          (error instanceof FamilyApiError && [404, 409].includes(error.status))
        ) {
          setRemoteState("contract_blocked");
          setMessage(
            "服务端没有返回可核验的人工任务凭据，已停止继续。请刷新测评结果或联系人工支持。",
          );
          return;
        }
        if (error instanceof FamilyApiError && error.status === 403) {
          setRemoteState("denied");
          setMessage("当前家庭授权或访问范围不允许读取这份支持方向。");
          return;
        }
        setRemoteState("error");
        setMessage("暂时无法读取这次家庭解读，请稍后重试。");
      });

    return () => {
      active = false;
      flow?.invalidate();
    };
  }, [familyId, session.status, session.token]);

  const decide = async (outcome: "ACCEPT" | "REJECT") => {
    if (confirmed && outcome === "ACCEPT") {
      router.push("/ui/UI-04" as Href);
      return;
    }
    if (
      session.status !== "connected" ||
      !session.token ||
      !familyId ||
      !remote ||
      !hypothesis ||
      remoteState !== "ready"
    ) {
      setDecisionState("contract_blocked");
      setMessage(
        "当前支持方向没有完整的家庭、假设和人工任务绑定，已停止继续。",
      );
      return;
    }
    if (outcome === "REJECT" && !rejectionReason.trim()) {
      setDecisionState("contract_blocked");
      setMessage("请填写你不接受这份支持方向的真实原因。");
      return;
    }

    setDecisionState("saving");
    setMessage(null);
    try {
      const result = await flowRef.current!.decide({
        token: session.token,
        projection: remote,
        outcome,
        ...(outcome === "REJECT" ? { reason: rejectionReason } : {}),
      });
      if (result.status === "REJECTED") {
        setDecisionState("rejected");
        setMessage(
          "已记录你的拒绝原因。这份支持方向已终止，不会创建成长意向或启动方案。",
        );
        return;
      }
      setUi03FlowContext(result);
      setDecisionState("success");
      router.push("/ui/UI-04" as Href);
    } catch (error) {
      if (error instanceof Ui03FlowStaleError) return;
      if (isRetryableUi03FlowError(error)) {
        setDecisionState("retryable");
        setMessage(
          "网络请求超时。可以安全重试，系统会复用同一请求内容和幂等标识。",
        );
        return;
      }
      setDecisionState("contract_blocked");
      setMessage(
        "人工确认凭据已过期、冲突或与当前家庭不匹配，已停止继续。请重新加载这份解读。",
      );
    }
  };

  if (remoteState === "loading") {
    return (
      <ScreenContainer edges={["left", "right", "bottom"]}>
        <Stack.Screen
          options={{
            headerShown: true,
            title: "家庭支持理解",
            headerBackTitle: "返回",
          }}
        />
        <View style={styles.emptyPage}>
          <ActivityIndicator color={colors.tint} />
          <Text style={[styles.emptyTitle, { color: colors.text }]}>
            正在读取可审阅的支持假设
          </Text>
          <Text style={[styles.emptyText, { color: colors.muted }]}>
            只有服务端同时返回人工任务凭据时，才能继续确认。
          </Text>
        </View>
      </ScreenContainer>
    );
  }

  const unavailable = remoteState !== "ready" || !hypothesis;
  const submittedAt = formatDate(
    hypothesis?.source_refs.assessment_submitted_at,
  );
  const summaryRows = [
    hypothesis?.subject_display_name
      ? `姓名：${hypothesis.subject_display_name}`
      : null,
    submittedAt ? `测评时间：${submittedAt}` : null,
    hypothesis?.source_refs.tool_version
      ? `测评版本：v${hypothesis.source_refs.tool_version}`
      : null,
    hypothesis
      ? `AI状态：${formatAiState(remote?.ai_state ?? "NOT_INVOKED")}`
      : null,
  ].filter((row): row is string => Boolean(row));

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen
        options={{
          headerShown: true,
          title: "家庭支持理解",
          headerBackTitle: "返回",
          headerRight: () => (
            <IconSymbol name="ellipsis" size={24} color="#111827" />
          ),
        }}
      />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.empathyCard} accessibilityRole="summary">
          <Text style={styles.empathyTitle}>先接住这份无奈和疲惫</Text>
          <Text style={styles.empathyText}>
            你不需要一次解决所有问题。我们先一起看清一个可讨论的方向，再由你明确接受或拒绝。
          </Text>
        </View>

        {unavailable ? (
          <View
            style={
              remoteState === "contract_blocked"
                ? styles.errorNotice
                : styles.previewNotice
            }
          >
            <Text
              style={
                remoteState === "contract_blocked"
                  ? styles.errorNoticeTitle
                  : styles.previewNoticeTitle
              }
            >
              {remoteState === "empty"
                ? "还没有提交的家庭测评"
                : remoteState === "denied"
                  ? "暂时不能展示这次解读"
                  : remoteState === "contract_blocked"
                    ? "确认契约已阻断"
                    : "读取失败"}
            </Text>
            <Text
              style={
                remoteState === "contract_blocked"
                  ? styles.errorNoticeText
                  : styles.previewNoticeText
              }
            >
              {message ??
                "完成并提交一次家庭测评后，系统才会基于真实回答整理支持方向。"}
            </Text>
          </View>
        ) : null}

        <View style={styles.assessmentSummary}>
          <View style={styles.summaryAvatar}>
            <IconSymbol
              name="person.crop.circle.fill"
              size={58}
              color="#2563EB"
            />
          </View>
          <View style={styles.summaryCopy}>
            <Text style={styles.summaryBadge}>
              {hypothesis ? "可审阅支持假设" : "测评后生成"}
            </Text>
            <Text style={styles.summaryTitle}>
              {hypothesis?.title ?? "家庭支持理解"}
            </Text>
            {summaryRows.map((row) => (
              <Text key={row} style={styles.summaryMeta}>
                {row}
              </Text>
            ))}
          </View>
        </View>

        <Text style={[styles.sectionTitle, { color: colors.text }]}>
          证据与支持方向
        </Text>
        {hypothesis ? (
          <View style={styles.directionCard}>
            <Text style={styles.directionTitle}>核心问题</Text>
            <Text style={[styles.directionText, { color: colors.text }]}>
              {hypothesis.statement}
            </Text>
          </View>
        ) : (
          <View style={styles.supportEmpty}>
            <Text style={styles.supportEmptyTitle}>完成测评后显示支持方向</Text>
            <Text style={styles.supportEmptyText}>
              这里不会预填家庭分数，也不会替家庭或孩子下诊断结论。
            </Text>
          </View>
        )}

        {hypothesis?.limitations.length ? (
          <>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>
              理解边界
            </Text>
            <View style={styles.evidenceCard}>
              {hypothesis.limitations.map((item) => (
                <Text key={item} style={styles.evidenceMeta}>
                  • {item}
                </Text>
              ))}
            </View>
          </>
        ) : null}

        {hypothesis ? (
          <View style={styles.safetyNotice}>
            <Text style={styles.safetyNoticeTitle}>需要你明确确认</Text>
            <Text style={styles.safetyNoticeText}>
              接受会先形成可审计的人工决定，再以服务端回执创建成长意向；拒绝会终止流程，不会被当成“稍后再说”。
              只有两段确认都成功后，系统才会生成个性化方案。
            </Text>
          </View>
        ) : null}

        {message && !unavailable ? (
          <View
            style={
              decisionState === "rejected"
                ? styles.previewNotice
                : styles.errorNotice
            }
          >
            <Text
              style={
                decisionState === "rejected"
                  ? styles.previewNoticeText
                  : styles.errorNoticeText
              }
            >
              {message}
            </Text>
          </View>
        ) : null}

        <Pressable
          accessibilityRole="button"
          disabled={
            unavailable ||
            decisionState === "saving" ||
            decisionState === "rejected"
          }
          onPress={() => void decide("ACCEPT")}
          style={({ pressed }) => [
            styles.primaryButton,
            { backgroundColor: colors.tint },
            (pressed ||
              unavailable ||
              decisionState === "saving" ||
              decisionState === "rejected") &&
              styles.disabledButton,
          ]}
        >
          <IconSymbol name="checkmark.circle.fill" size={18} color="#FFFFFF" />
          <Text style={styles.primaryButtonText}>
            {decisionState === "saving"
              ? "正在核验并确认"
              : confirmed
                ? "继续查看成长方案"
                : decisionState === "retryable"
                  ? "安全重试确认"
                  : "接受这份支持方向并继续"}
          </Text>
        </Pressable>

        {hypothesis && decisionState !== "rejected" ? (
          <View style={styles.rejectCard}>
            <Text style={styles.rejectTitle}>不接受这份支持方向</Text>
            <TextInput
              accessibilityLabel="拒绝原因"
              multiline
              maxLength={1000}
              onChangeText={setRejectionReason}
              placeholder="请填写真实原因，例如：这与我们观察到的情况不一致"
              style={styles.reasonInput}
              value={rejectionReason}
            />
            <Pressable
              accessibilityRole="button"
              disabled={decisionState === "saving" || !rejectionReason.trim()}
              onPress={() => void decide("REJECT")}
              style={({ pressed }) => [
                styles.rejectButton,
                (pressed || !rejectionReason.trim()) && styles.disabledButton,
              ]}
            >
              <Text style={styles.rejectButtonText}>提交拒绝并终止</Text>
            </Pressable>
          </View>
        ) : null}

        <Pressable
          accessibilityRole="button"
          onPress={() => router.back()}
          style={styles.deferButton}
        >
          <Text style={[styles.deferText, { color: colors.muted }]}>
            先放一放，不提交决定
          </Text>
        </Pressable>
        <Text style={[styles.boundaryText, { color: colors.muted }]}>
          以上内容用于家庭支持参考，不是儿童诊断结论、能力测验或排名。
        </Text>
      </ScrollView>
    </ScreenContainer>
  );
}

function formatDate(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function formatAiState(value: Ui03GrowthHypothesisProjection["ai_state"]) {
  if (value === "MODEL_DRAFT_READY") return "模型草稿已生成，等待人工确认";
  if (value === "MODEL_GATEWAY_BLOCKED") return "模型网关已拦截";
  return "尚未调用模型";
}

const styles = StyleSheet.create({
  content: {
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 34,
    gap: 16,
    backgroundColor: "#FFFFFF",
  },
  empathyCard: {
    borderRadius: 16,
    backgroundColor: "#FFF7EE",
    borderWidth: 1,
    borderColor: "#F5D5B8",
    padding: 14,
    gap: 4,
  },
  empathyTitle: {
    color: "#8A4B00",
    fontSize: 15,
    lineHeight: 21,
    fontWeight: "900",
  },
  empathyText: {
    color: "#6F532B",
    fontSize: 13,
    lineHeight: 19,
    fontWeight: "700",
  },
  errorNotice: {
    borderRadius: 16,
    backgroundColor: "#FFF1F0",
    borderWidth: 1,
    borderColor: "#F2B8B5",
    padding: 14,
    gap: 4,
  },
  errorNoticeTitle: {
    color: "#A33A35",
    fontSize: 14,
    lineHeight: 20,
    fontWeight: "900",
  },
  errorNoticeText: {
    color: "#7E4D4A",
    fontSize: 12,
    lineHeight: 18,
    fontWeight: "700",
  },
  supportEmpty: {
    minHeight: 154,
    borderRadius: 16,
    backgroundColor: "#F8FAFC",
    borderWidth: 1,
    borderColor: "#E3EAF2",
    padding: 18,
    justifyContent: "center",
    gap: 7,
  },
  supportEmptyTitle: {
    color: "#344054",
    fontSize: 16,
    lineHeight: 22,
    fontWeight: "900",
    textAlign: "center",
  },
  supportEmptyText: {
    color: "#68727D",
    fontSize: 12,
    lineHeight: 18,
    fontWeight: "700",
    textAlign: "center",
  },
  safetyNotice: {
    borderRadius: 16,
    backgroundColor: "#FFF4E5",
    borderWidth: 1,
    borderColor: "#F3C879",
    padding: 14,
    gap: 4,
  },
  safetyNoticeTitle: {
    color: "#8A4B00",
    fontSize: 14,
    lineHeight: 20,
    fontWeight: "900",
  },
  safetyNoticeText: {
    color: "#6F532B",
    fontSize: 12,
    lineHeight: 18,
    fontWeight: "700",
  },
  emptyPage: { flex: 1, padding: 24, justifyContent: "center", gap: 16 },
  emptyTitle: { fontSize: 25, lineHeight: 34, fontWeight: "800" },
  emptyText: { fontSize: 15, lineHeight: 23 },
  previewNotice: {
    borderRadius: 16,
    backgroundColor: "#FFF6DF",
    borderWidth: 1,
    borderColor: "#F8DE94",
    padding: 14,
    gap: 4,
  },
  previewNoticeTitle: {
    color: "#8A5A00",
    fontSize: 14,
    lineHeight: 20,
    fontWeight: "900",
  },
  previewNoticeText: {
    color: "#6F5A36",
    fontSize: 12,
    lineHeight: 18,
    fontWeight: "700",
  },
  assessmentSummary: {
    minHeight: 138,
    borderRadius: 16,
    backgroundColor: "#E8F2FF",
    padding: 16,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    shadowColor: "#B9DCFF",
    shadowOpacity: 0.18,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 10 },
    elevation: 4,
  },
  summaryAvatar: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: "#FFFFFF",
    alignItems: "center",
    justifyContent: "center",
  },
  summaryCopy: { flex: 1, gap: 4 },
  summaryBadge: {
    alignSelf: "flex-start",
    overflow: "hidden",
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 3,
    backgroundColor: "#FFFFFF80",
    color: "#2563EB",
    fontSize: 11,
    lineHeight: 15,
    fontWeight: "800",
  },
  summaryTitle: {
    color: "#09295A",
    fontSize: 18,
    lineHeight: 24,
    fontWeight: "800",
  },
  summaryMeta: {
    color: "#5B7091",
    fontSize: 12,
    lineHeight: 17,
    fontWeight: "700",
  },
  sectionTitle: { fontSize: 18, lineHeight: 25, fontWeight: "800" },
  evidenceCard: {
    borderRadius: 14,
    backgroundColor: "#F5F9FF",
    borderWidth: 1,
    borderColor: "#D9E8FA",
    padding: 14,
    gap: 7,
  },
  evidenceMeta: {
    color: "#5B7091",
    fontSize: 12,
    lineHeight: 18,
    fontWeight: "700",
  },
  directionCard: {
    borderRadius: 14,
    backgroundColor: "#F7FBF8",
    borderWidth: 1,
    borderColor: "#D8EBDD",
    padding: 14,
    gap: 8,
  },
  directionTitle: {
    color: "#23633B",
    fontSize: 15,
    lineHeight: 21,
    fontWeight: "900",
  },
  directionText: { fontSize: 13, lineHeight: 20, fontWeight: "700" },
  primaryButton: {
    minHeight: 52,
    borderRadius: 26,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 7,
    marginTop: 2,
  },
  primaryButtonText: {
    color: "#FFFFFF",
    fontSize: 16,
    lineHeight: 22,
    fontWeight: "800",
  },
  rejectCard: {
    borderRadius: 16,
    borderWidth: 1,
    borderColor: "#E1E6EC",
    padding: 14,
    gap: 10,
  },
  rejectTitle: {
    color: "#344054",
    fontSize: 14,
    lineHeight: 20,
    fontWeight: "900",
  },
  reasonInput: {
    minHeight: 82,
    borderWidth: 1,
    borderColor: "#CDD5DF",
    borderRadius: 12,
    padding: 12,
    color: "#1F2937",
    textAlignVertical: "top",
  },
  rejectButton: {
    minHeight: 44,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: "#B42318",
    alignItems: "center",
    justifyContent: "center",
  },
  rejectButtonText: {
    color: "#B42318",
    fontSize: 14,
    lineHeight: 20,
    fontWeight: "800",
  },
  disabledButton: { opacity: 0.5 },
  deferButton: {
    minHeight: 44,
    alignItems: "center",
    justifyContent: "center",
  },
  deferText: { fontSize: 13, lineHeight: 18, fontWeight: "700" },
  boundaryText: {
    marginTop: -6,
    fontSize: 11,
    lineHeight: 17,
    textAlign: "center",
  },
});
