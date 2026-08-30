import { Stack } from "expo-router";
import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { ScreenContainer } from "@/components/screen-container";
import { IconSymbol } from "@/components/ui/icon-symbol";
import { useColors } from "@/hooks/use-colors";
import { familyApi, FamilyApiError, type FamilyContextSummary } from "@/lib/family/family-api-client";
import { useFamilyApiSession } from "@/lib/family/family-api-session";

type ConsentState = "GRANTED" | "REQUIRED" | "REVOKED" | "REVIEW_REQUIRED" | "EXPIRED";
type AuthorizedContextState = "AUTHORIZED" | "DENIED" | "WITHDRAWN" | "EXPIRED" | "NOT_RETURNED";
type Ui03ViewState =
  | "loading"
  | "family_selection"
  | "empty"
  | "success"
  | "denied"
  | "withdrawn"
  | "expired"
  | "unauthorized"
  | "forbidden"
  | "conflict"
  | "error"
  | "demo_only";

interface Ui03ProcessingPurpose {
  purpose_ref: string;
  title?: string;
  description: string;
  data_scope?: string[];
  retention?: string;
  withdrawal?: string;
}

interface Ui03ConsentProjection {
  required_purposes?: string[];
  state: ConsentState;
  policy_version?: string;
}

interface Ui03AuthorizedContextProjection {
  state: AuthorizedContextState;
  family_id?: string;
  role?: string;
}

interface Ui03AssessmentProjection {
  availability: "AVAILABLE" | "CONSENT_REQUIRED" | "NO_SUBJECT" | "POLICY_BLOCKED";
  subjects: { person_id: string; display_name: string; availability: "AVAILABLE" | "CONSENT_REQUIRED" }[];
  tool: { tool_ref: string; version_no: number; title: string; purpose: string } | null;
  consent_state?: Ui03ConsentProjection;
}

interface Ui03HypothesisProjection {
  projection_version: "UI03_GROWTH_HYPOTHESIS_V1";
  availability: "READY" | "NO_SUBMITTED_ASSESSMENT" | "POLICY_BLOCKED" | "CONSENT_WITHDRAWN" | "EXPIRED" | "EMPTY" | "DENIED";
  entry_state?: "READY" | "EMPTY" | "CONSENT_REQUIRED" | "REVIEW_REQUIRED" | "FORBIDDEN" | "STALE" | "ERROR";
  consent_state?: Ui03ConsentProjection;
  authorized_context?: Ui03AuthorizedContextProjection;
  processing_purposes?: Ui03ProcessingPurpose[];
  hypothesis: {
    subject_display_name?: string;
    title: string;
    statement: string;
    limitations: string[];
    fact_boundary?: "HYPOTHESIS_NOT_FACT_OR_DIAGNOSIS";
    source_refs?: { assessment_session_id?: string; assessment_submitted_at?: string | null };
  } | null;
}

export interface Ui03StateInput {
  phase?: "loading";
  errorStatus?: number;
  errorCode?: string;
  availability?: string;
  entryState?: string;
  consentState?: string;
  authorizedContextState?: string;
  hasProjection?: boolean;
}

export function mapUi03ViewState(input: Ui03StateInput): Ui03ViewState {
  if (input.phase === "loading") return "loading";
  const errorCode = input.errorCode?.toUpperCase() ?? "";
  if (input.errorStatus === 401) return "unauthorized";
  if (input.errorStatus === 403) return "forbidden";
  if (input.errorStatus === 409) return "conflict";
  if (input.errorStatus === 410 || errorCode.includes("EXPIRED")) return "expired";
  if (input.errorStatus !== undefined) return "error";

  const entryState = input.entryState?.toUpperCase();
  const consentState = input.consentState?.toUpperCase();
  const authorizedContextState = input.authorizedContextState?.toUpperCase();
  const availability = input.availability?.toUpperCase();

  if (entryState === "STALE" || entryState === "REVIEW_REQUIRED" || entryState === "ERROR") return "error";
  if (consentState === "EXPIRED" || authorizedContextState === "EXPIRED" || availability === "EXPIRED") return "expired";
  if (consentState === "REVOKED" || authorizedContextState === "WITHDRAWN" || availability === "CONSENT_WITHDRAWN") return "withdrawn";
  if (entryState === "FORBIDDEN" || entryState === "CONSENT_REQUIRED" || consentState === "REQUIRED" || consentState === "REVIEW_REQUIRED" || availability === "POLICY_BLOCKED" || availability === "DENIED") return "denied";
  if (entryState === "EMPTY" || availability === "EMPTY" || availability === "NO_SUBMITTED_ASSESSMENT" || availability === "NO_SUBJECT") return "empty";
  if ((entryState === "READY" || availability === "READY") && input.hasProjection) return "success";
  return "error";
}

export default function GrowthExplanationScreen() {
  const colors = useColors();
  const session = useFamilyApiSession();
  const [viewState, setViewState] = useState<Ui03ViewState>("loading");
  const [assessment, setAssessment] = useState<Ui03AssessmentProjection | null>(null);
  const [projection, setProjection] = useState<Ui03HypothesisProjection | null>(null);
  const [error, setError] = useState<FamilyApiError | null>(null);
  const [purposeOpen, setPurposeOpen] = useState(true);
  const [retryNonce, setRetryNonce] = useState(0);

  useEffect(() => {
    let active = true;
    setViewState("loading");
    setAssessment(null);
    setProjection(null);
    setError(null);

    if (session.status === "loading") return () => { active = false; };
    if (session.status === "local_synthetic") {
      setViewState("demo_only");
      return () => { active = false; };
    }
    if (session.status === "family_selection") {
      setViewState("family_selection");
      return () => { active = false; };
    }
    if (session.status === "no_family") {
      setViewState("empty");
      return () => { active = false; };
    }
    if (session.status === "error") {
      const sessionError = session.error ?? new FamilyApiError("Family API 会话错误", 0, "FAMILY_API_SESSION_ERROR", null);
      setError(sessionError);
      setViewState(mapUi03ViewState({ errorStatus: sessionError.status, errorCode: sessionError.code }));
      return () => { active = false; };
    }
    if (session.status !== "connected" || !session.token || !session.selectedFamily) {
      setViewState("error");
      return () => { active = false; };
    }

    const load = async () => {
      try {
        const [assessmentResult, projectionResult] = await Promise.all([
          familyApi.getFamilyAssessment<Ui03AssessmentProjection>(session.token!, session.selectedFamily!.family_id),
          familyApi.getGrowthHypothesis<Ui03HypothesisProjection>(session.token!, session.selectedFamily!.family_id),
        ]);
        if (!active) return;
        const nextConsent = projectionResult.consent_state?.state ?? assessmentResult.consent_state?.state;
        const nextViewState = mapUi03ViewState({
          availability: projectionResult.availability,
          entryState: projectionResult.entry_state,
          consentState: nextConsent,
          authorizedContextState: projectionResult.authorized_context?.state,
          hasProjection: Boolean(projectionResult.hypothesis),
        });
        setAssessment(assessmentResult);
        setProjection(projectionResult);
        if (nextViewState === "success" && !getPurposeText(assessmentResult, projectionResult)) {
          setError(new FamilyApiError("处理目的缺失", 0, "PROVENANCE_INCOMPLETE", null));
          setViewState("error");
          return;
        }
        setViewState(nextViewState);
      } catch (cause) {
        if (!active) return;
        const nextError = asFamilyApiError(cause);
        setError(nextError);
        setViewState(mapUi03ViewState({ errorStatus: nextError.status, errorCode: nextError.code }));
      }
    };

    void load();
    return () => { active = false; };
  }, [retryNonce, session.selectedFamily, session.status, session.token]);

  const retry = () => setRetryNonce((value) => value + 1);

  if (viewState === "loading") return <LoadingState colors={colors} />;
  if (viewState === "family_selection") return <FamilySelectionState contexts={session.contexts} onSelect={session.selectFamily} colors={colors} />;
  if (viewState === "demo_only") return <DemoOnlyState onConnect={session.connectDevSession} colors={colors} />;
  if (viewState === "empty") return <EmptyState onRetry={retry} colors={colors} />;
  if (viewState === "unauthorized" || viewState === "forbidden" || viewState === "conflict" || viewState === "error") {
    return <ErrorState state={viewState} error={error} onRetry={retry} colors={colors} />;
  }

  const purposeText = getPurposeText(assessment, projection);
  const consentState = projection?.consent_state?.state ?? assessment?.consent_state?.state ?? "REVIEW_REQUIRED";
  const authorizedContext = projection?.authorized_context;
  const hypothesis = projection?.hypothesis;

  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: true, title: "VS-GROWTH-01", headerBackTitle: "返回" }} />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.headerRow}>
          <View style={styles.headerCopy}>
            <Text style={[styles.eyebrow, { color: colors.tint }]}>VS-GROWTH-01</Text>
            <Text style={[styles.title, { color: colors.text }]}>家庭成长支持</Text>
            <Text style={[styles.subtitle, { color: colors.muted }]}>成人先选择家庭，再查看处理目的和授权状态。</Text>
          </View>
          <IconSymbol name="shield.fill" size={28} color={colors.tint} />
        </View>

        <FamilyContextCard context={session.selectedFamily} colors={colors} />

        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <View style={styles.cardHeaderCopy}>
              <Text style={[styles.cardTitle, { color: colors.text }]}>处理目的</Text>
              <Text style={[styles.cardHint, { color: colors.muted }]}>以下内容只来自 canonical API 返回；未返回的字段不在本地补齐。</Text>
            </View>
            <Pressable accessibilityRole="button" accessibilityState={{ expanded: purposeOpen }} onPress={() => setPurposeOpen((value) => !value)}>
              <Text style={[styles.link, { color: colors.tint }]}>{purposeOpen ? "收起" : "查看"}</Text>
            </Pressable>
          </View>
          {purposeOpen ? <PurposeContent purposeText={purposeText} purposes={projection?.processing_purposes} colors={colors} /> : null}
        </View>

        <ConsentCard state={consentState} colors={colors} />
        <AuthorizedContextCard context={authorizedContext} colors={colors} />

        {viewState === "success" && hypothesis ? <HypothesisCard hypothesis={hypothesis} colors={colors} /> : null}
        {viewState === "denied" ? <BlockedNotice title="当前未获得授权" detail="canonical API 返回了拒绝或需要同意的状态；本页不会通过勾选框代替 ConsentGrant。" /> : null}
        {viewState === "withdrawn" ? <BlockedNotice title="授权已撤回" detail="撤回状态立即阻止继续读取；如需继续，请由 canonical Consent 流程重新处理。" /> : null}
        {viewState === "expired" ? <BlockedNotice title="授权已过期" detail="当前授权上下文已过期；本页不会沿用过期上下文或本地缓存。" /> : null}

        <ConsentActionBoundary colors={colors} />
        <Text style={[styles.boundary, { color: colors.muted }]}>本页面只读取家庭范围内的 canonical projection，不创建 Family、Consent、授权上下文或成长事实。</Text>
      </ScrollView>
    </ScreenContainer>
  );
}

function LoadingState({ colors }: { colors: ReturnType<typeof useColors> }) {
  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: true, title: "VS-GROWTH-01", headerBackTitle: "返回" }} />
      <View style={styles.centerState}>
        <ActivityIndicator color={colors.tint} />
        <Text style={[styles.stateTitle, { color: colors.text }]}>正在读取家庭上下文</Text>
        <Text style={[styles.stateDetail, { color: colors.muted }]}>正在等待 Family API 返回家庭范围、处理目的和授权状态。</Text>
      </View>
    </ScreenContainer>
  );
}

function FamilySelectionState({ contexts, onSelect, colors }: { contexts: FamilyContextSummary[]; onSelect: (familyId: string) => Promise<void>; colors: ReturnType<typeof useColors> }) {
  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: true, title: "选择家庭", headerBackTitle: "返回" }} />
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={[styles.eyebrow, { color: colors.tint }]}>VS-GROWTH-01</Text>
        <Text style={[styles.title, { color: colors.text }]}>选择家庭</Text>
        <Text style={[styles.subtitle, { color: colors.muted }]}>请选择 Family API 已返回且当前成人有权限访问的家庭上下文。</Text>
        {contexts.map((context) => (
          <Pressable key={context.family_id} accessibilityRole="button" onPress={() => void onSelect(context.family_id)} style={({ pressed }) => [styles.familyOption, { borderColor: colors.border, backgroundColor: colors.surface }, pressed && styles.pressed]}>
            <IconSymbol name="person.2.fill" size={24} color={colors.tint} />
            <View style={styles.familyOptionCopy}>
              <Text style={[styles.familyOptionTitle, { color: colors.text }]}>家庭 {context.family_id}</Text>
              <Text style={[styles.familyOptionMeta, { color: colors.muted }]}>当前角色：{context.role}</Text>
            </View>
            <IconSymbol name="chevron.right" size={18} color={colors.muted} />
          </Pressable>
        ))}
        <View style={styles.boundaryCard}>
          <Text style={[styles.boundaryCardTitle, { color: colors.text }]}>创建家庭</Text>
          <Text style={[styles.boundaryCardDetail, { color: colors.muted }]}>现有 canonical client 未提供 CreateFamily 动作；本页不在本地创建家庭或伪造家庭上下文。</Text>
          <Pressable disabled style={[styles.secondaryButton, { borderColor: colors.border }]}><Text style={[styles.secondaryButtonText, { color: colors.muted }]}>创建家庭（需 Family API）</Text></Pressable>
        </View>
      </ScrollView>
    </ScreenContainer>
  );
}

function DemoOnlyState({ onConnect, colors }: { onConnect: () => Promise<void>; colors: ReturnType<typeof useColors> }) {
  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: true, title: "VS-GROWTH-01", headerBackTitle: "返回" }} />
      <View style={styles.centerState}>
        <Text style={styles.demoBadge}>DEMO_ONLY</Text>
        <Text style={[styles.stateTitle, { color: colors.text }]}>未连接 canonical API</Text>
        <Text style={[styles.stateDetail, { color: colors.muted }]}>当前只展示流程边界，不提供 synthetic Family、Consent、处理目的或 authorized context，也不会把演示内容当作真实证据。</Text>
        <Pressable onPress={() => void onConnect()} style={({ pressed }) => [styles.primaryButton, { backgroundColor: colors.tint }, pressed && styles.pressed]}><Text style={styles.primaryButtonText}>连接 Family API</Text></Pressable>
      </View>
    </ScreenContainer>
  );
}

function EmptyState({ onRetry, colors }: { onRetry: () => void; colors: ReturnType<typeof useColors> }) {
  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: true, title: "VS-GROWTH-01", headerBackTitle: "返回" }} />
      <View style={styles.centerState}>
        <IconSymbol name="person.2.fill" size={36} color={colors.muted} />
        <Text style={[styles.stateTitle, { color: colors.text }]}>尚未返回家庭上下文</Text>
        <Text style={[styles.stateDetail, { color: colors.muted }]}>当前没有可供选择或读取的 Family API 家庭，不会在本地创建家庭。</Text>
        <Pressable onPress={onRetry} style={({ pressed }) => [styles.secondaryButton, { borderColor: colors.border }, pressed && styles.pressed]}><Text style={[styles.secondaryButtonText, { color: colors.text }]}>重新读取</Text></Pressable>
      </View>
    </ScreenContainer>
  );
}

function ErrorState({ state, error, onRetry, colors }: { state: Extract<Ui03ViewState, "unauthorized" | "forbidden" | "conflict" | "error">; error: FamilyApiError | null; onRetry: () => void; colors: ReturnType<typeof useColors> }) {
  const copy = state === "unauthorized"
    ? { title: "登录已失效", detail: "请重新连接账号；未获得认证上下文前不会读取家庭数据。" }
    : state === "forbidden"
      ? { title: "无权访问当前家庭", detail: "当前账号没有这个家庭范围的读取权限，服务端拒绝了请求。" }
      : state === "conflict"
        ? { title: "家庭上下文发生冲突", detail: "当前请求与服务端状态不一致，请重新读取后再继续。" }
        : { title: "暂时无法读取", detail: "canonical API 没有返回可用 projection；本页不会把错误静默成空态或成功。" };
  return (
    <ScreenContainer edges={["left", "right", "bottom"]}>
      <Stack.Screen options={{ headerShown: true, title: "VS-GROWTH-01", headerBackTitle: "返回" }} />
      <View style={styles.centerState}>
        <Text style={[styles.errorBadge, { color: "#B42318", backgroundColor: "#FEE4E2" }]}>{errorLabel(state, error)}</Text>
        <Text style={[styles.stateTitle, { color: colors.text }]}>{copy.title}</Text>
        <Text style={[styles.stateDetail, { color: colors.muted }]}>{copy.detail}</Text>
        <Pressable onPress={onRetry} style={({ pressed }) => [styles.primaryButton, { backgroundColor: colors.tint }, pressed && styles.pressed]}><Text style={styles.primaryButtonText}>重新读取</Text></Pressable>
      </View>
    </ScreenContainer>
  );
}

function FamilyContextCard({ context, colors }: { context: FamilyContextSummary | null; colors: ReturnType<typeof useColors> }) {
  return (
    <View style={[styles.contextCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      <View style={styles.contextIcon}><IconSymbol name="person.2.fill" size={24} color={colors.tint} /></View>
      <View style={styles.contextCopy}>
        <Text style={[styles.contextLabel, { color: colors.muted }]}>当前家庭上下文</Text>
        <Text style={[styles.contextTitle, { color: colors.text }]}>{context ? `家庭 ${context.family_id}` : "未选择家庭"}</Text>
        <Text style={[styles.contextMeta, { color: colors.muted }]}>{context ? `成人角色：${context.role}` : "等待 canonical API 返回"}</Text>
      </View>
    </View>
  );
}

function PurposeContent({ purposeText, purposes, colors }: { purposeText: string | null; purposes?: Ui03ProcessingPurpose[]; colors: ReturnType<typeof useColors> }) {
  return (
    <View style={styles.purposeContent}>
      <Text style={[styles.purposeText, { color: colors.text }]}>{purposeText ?? "canonical API 未返回处理目的"}</Text>
      {purposes?.map((purpose) => (
        <View key={purpose.purpose_ref} style={styles.purposeItem}>
          <Text style={[styles.purposeItemTitle, { color: colors.text }]}>{purpose.title ?? purpose.purpose_ref}</Text>
          <Text style={[styles.purposeItemDetail, { color: colors.muted }]}>{purpose.description}</Text>
          {purpose.data_scope?.length ? <Text style={[styles.purposeItemDetail, { color: colors.muted }]}>数据范围：{purpose.data_scope.join("、")}</Text> : null}
          {purpose.retention ? <Text style={[styles.purposeItemDetail, { color: colors.muted }]}>留存：{purpose.retention}</Text> : null}
          {purpose.withdrawal ? <Text style={[styles.purposeItemDetail, { color: colors.muted }]}>撤回：{purpose.withdrawal}</Text> : null}
        </View>
      ))}
    </View>
  );
}

function ConsentCard({ state, colors }: { state: ConsentState; colors: ReturnType<typeof useColors> }) {
  const copy = consentCopy(state);
  return (
    <View style={[styles.card, { borderColor: state === "GRANTED" ? "#B7E3C2" : colors.border, backgroundColor: state === "GRANTED" ? "#F4FBF5" : colors.surface }]}>
      <View style={styles.cardHeader}>
        <View style={styles.cardHeaderCopy}>
          <Text style={[styles.cardTitle, { color: colors.text }]}>授权状态</Text>
          <Text style={[styles.cardHint, { color: colors.muted }]}>处理目的与授权状态由服务端返回，页面勾选不能替代 ConsentGrant。</Text>
        </View>
        <Text style={[styles.statePill, { color: copy.color, backgroundColor: copy.background }]}>{copy.label}</Text>
      </View>
      <Text style={[styles.cardDetail, { color: colors.muted }]}>{copy.detail}</Text>
    </View>
  );
}

function AuthorizedContextCard({ context, colors }: { context?: Ui03AuthorizedContextProjection; colors: ReturnType<typeof useColors> }) {
  const returned = context?.state === "AUTHORIZED";
  return (
    <View style={[styles.card, { borderColor: returned ? "#B7E3C2" : colors.border, backgroundColor: returned ? "#F4FBF5" : colors.surface }]}>
      <Text style={[styles.cardTitle, { color: colors.text }]}>authorized context</Text>
      <Text style={[styles.cardDetail, { color: colors.muted }]}>{returned ? "canonical API 已返回当前家庭的 authorized context。" : "canonical API 未返回可用 authorized context；本地不会补发或推断授权上下文。"}</Text>
      {context?.family_id ? <Text style={[styles.cardHint, { color: colors.muted }]}>家庭：{context.family_id}{context.role ? ` · 角色：${context.role}` : ""}</Text> : null}
    </View>
  );
}

function HypothesisCard({ hypothesis, colors }: { hypothesis: NonNullable<Ui03HypothesisProjection["hypothesis"]>; colors: ReturnType<typeof useColors> }) {
  return (
    <View style={[styles.card, { borderColor: colors.border, backgroundColor: colors.surface }]}>
      <Text style={[styles.cardTitle, { color: colors.text }]}>家庭支持方向</Text>
      <Text style={[styles.hypothesisTitle, { color: colors.text }]}>{hypothesis.title}</Text>
      <Text style={[styles.cardDetail, { color: colors.text }]}>{hypothesis.statement}</Text>
      {hypothesis.source_refs?.assessment_session_id ? <Text style={[styles.cardHint, { color: colors.muted }]}>来源测评：{hypothesis.source_refs.assessment_session_id}</Text> : null}
      {hypothesis.limitations.map((item) => <Text key={item} style={[styles.cardHint, { color: colors.muted }]}>• {item}</Text>)}
      <Text style={[styles.boundaryNote, { color: colors.muted }]}>{hypothesis.fact_boundary === "HYPOTHESIS_NOT_FACT_OR_DIAGNOSIS" ? "这是带来源的家庭支持假设，不是事实、诊断或结果结论。" : "仅展示服务端返回的受限解释内容。"}</Text>
    </View>
  );
}

function BlockedNotice({ title, detail }: { title: string; detail: string }) {
  return <View style={styles.blockedNotice}><Text style={styles.blockedTitle}>{title}</Text><Text style={styles.blockedDetail}>{detail}</Text></View>;
}

function ConsentActionBoundary({ colors }: { colors: ReturnType<typeof useColors> }) {
  return (
    <View style={[styles.actionBoundary, { borderColor: colors.border, backgroundColor: colors.surface }]}>
      <Text style={[styles.cardTitle, { color: colors.text }]}>同意 / 拒绝 / 撤回</Text>
      <Text style={[styles.cardDetail, { color: colors.muted }]}>现有 canonical client 没有 Consent 授予、拒绝或撤回动作端点。三个动作保持停止态，直到服务端提供对应 Named Action；点击或本地勾选不会改变授权事实。</Text>
      <View style={styles.actionRow}>
        <Pressable disabled style={[styles.actionButton, { borderColor: colors.border }]}><Text style={[styles.actionButtonText, { color: colors.muted }]}>同意</Text></Pressable>
        <Pressable disabled style={[styles.actionButton, { borderColor: colors.border }]}><Text style={[styles.actionButtonText, { color: colors.muted }]}>拒绝</Text></Pressable>
        <Pressable disabled style={[styles.actionButton, { borderColor: colors.border }]}><Text style={[styles.actionButtonText, { color: colors.muted }]}>撤回</Text></Pressable>
      </View>
    </View>
  );
}

function getPurposeText(assessment: Ui03AssessmentProjection | null, projection: Ui03HypothesisProjection | null) {
  return projection?.processing_purposes?.[0]?.description ?? assessment?.tool?.purpose ?? null;
}

function consentCopy(state: ConsentState) {
  if (state === "GRANTED") return { label: "已同意", detail: "canonical API 返回当前目的范围内的有效授权。", color: "#19713A", background: "#DDF5E3" };
  if (state === "REVOKED") return { label: "已撤回", detail: "撤回后立即停止新的读取或处理。", color: "#B42318", background: "#FEE4E2" };
  if (state === "EXPIRED") return { label: "已过期", detail: "授权不再有效，不能沿用旧上下文。", color: "#8A5A00", background: "#FFF1C7" };
  if (state === "REQUIRED") return { label: "需要同意", detail: "服务端要求先完成对应目的的授权。", color: "#8A5A00", background: "#FFF1C7" };
  return { label: "待复核", detail: "授权状态不完整或需要人工/服务端复核。", color: "#6B46C1", background: "#EEE7FF" };
}

function errorLabel(state: Extract<Ui03ViewState, "unauthorized" | "forbidden" | "conflict" | "error">, error: FamilyApiError | null) {
  if (state === "unauthorized") return "401 UNAUTHENTICATED";
  if (state === "forbidden") return "403 FAMILY_FORBIDDEN";
  if (state === "conflict") return "409 VERSION_CONFLICT";
  return error?.code ?? "API_ERROR";
}

function asFamilyApiError(cause: unknown) {
  return cause instanceof FamilyApiError
    ? cause
    : new FamilyApiError(cause instanceof Error ? cause.message : "Family API 错误", 0, "FAMILY_API_ERROR", null);
}

const styles = StyleSheet.create({
  content: { paddingHorizontal: 16, paddingTop: 16, paddingBottom: 34, gap: 14, backgroundColor: "#FFFFFF" },
  headerRow: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 14 },
  headerCopy: { flex: 1, gap: 4 },
  eyebrow: { fontSize: 11, lineHeight: 16, fontWeight: "900", letterSpacing: 1.2 },
  title: { fontSize: 28, lineHeight: 35, fontWeight: "900" },
  subtitle: { fontSize: 13, lineHeight: 20, fontWeight: "600" },
  contextCard: { flexDirection: "row", alignItems: "center", gap: 12, borderWidth: 1, borderRadius: 16, padding: 14 },
  contextIcon: { width: 44, height: 44, borderRadius: 22, backgroundColor: "#EAF2FF", alignItems: "center", justifyContent: "center" },
  contextCopy: { flex: 1, gap: 2 },
  contextLabel: { fontSize: 11, lineHeight: 16, fontWeight: "700" },
  contextTitle: { fontSize: 17, lineHeight: 23, fontWeight: "900" },
  contextMeta: { fontSize: 12, lineHeight: 18, fontWeight: "600" },
  card: { borderWidth: 1, borderRadius: 16, padding: 14, gap: 9 },
  cardHeader: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: 12 },
  cardHeaderCopy: { flex: 1, gap: 3 },
  cardTitle: { fontSize: 16, lineHeight: 22, fontWeight: "900" },
  cardHint: { fontSize: 11, lineHeight: 17, fontWeight: "600" },
  cardDetail: { fontSize: 13, lineHeight: 20, fontWeight: "600" },
  link: { fontSize: 12, lineHeight: 18, fontWeight: "900" },
  purposeContent: { gap: 9 },
  purposeText: { fontSize: 14, lineHeight: 22, fontWeight: "700" },
  purposeItem: { gap: 3, borderTopWidth: 1, borderTopColor: "#E8EEF5", paddingTop: 9 },
  purposeItemTitle: { fontSize: 13, lineHeight: 19, fontWeight: "800" },
  purposeItemDetail: { fontSize: 12, lineHeight: 18, fontWeight: "600" },
  statePill: { borderRadius: 999, paddingHorizontal: 9, paddingVertical: 5, fontSize: 11, lineHeight: 16, fontWeight: "900" },
  blockedNotice: { borderRadius: 16, borderWidth: 1, borderColor: "#F3C879", backgroundColor: "#FFF7E6", padding: 14, gap: 4 },
  blockedTitle: { color: "#8A4B00", fontSize: 15, lineHeight: 21, fontWeight: "900" },
  blockedDetail: { color: "#6F532B", fontSize: 12, lineHeight: 18, fontWeight: "700" },
  hypothesisTitle: { fontSize: 18, lineHeight: 24, fontWeight: "900" },
  boundaryNote: { borderTopWidth: 1, borderTopColor: "#E8EEF5", paddingTop: 9, fontSize: 11, lineHeight: 17, fontWeight: "700" },
  actionBoundary: { borderWidth: 1, borderRadius: 16, padding: 14, gap: 9 },
  actionRow: { flexDirection: "row", gap: 8 },
  actionButton: { flex: 1, minHeight: 42, borderWidth: 1, borderRadius: 12, alignItems: "center", justifyContent: "center", backgroundColor: "#F4F6F8" },
  actionButtonText: { fontSize: 13, lineHeight: 18, fontWeight: "800" },
  boundary: { fontSize: 11, lineHeight: 17, textAlign: "center", fontWeight: "600" },
  centerState: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24, gap: 14 },
  stateTitle: { fontSize: 22, lineHeight: 29, fontWeight: "900", textAlign: "center" },
  stateDetail: { fontSize: 14, lineHeight: 22, textAlign: "center", fontWeight: "600" },
  primaryButton: { minHeight: 48, borderRadius: 24, paddingHorizontal: 20, alignItems: "center", justifyContent: "center" },
  primaryButtonText: { color: "#FFFFFF", fontSize: 14, lineHeight: 20, fontWeight: "900" },
  secondaryButton: { minHeight: 44, borderRadius: 12, borderWidth: 1, paddingHorizontal: 16, alignItems: "center", justifyContent: "center" },
  secondaryButtonText: { fontSize: 13, lineHeight: 19, fontWeight: "800" },
  demoBadge: { color: "#8A5A00", backgroundColor: "#FFF1C7", borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5, fontSize: 11, lineHeight: 16, fontWeight: "900", letterSpacing: 1 },
  errorBadge: { borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5, fontSize: 11, lineHeight: 16, fontWeight: "900" },
  familyOption: { minHeight: 70, borderWidth: 1, borderRadius: 16, padding: 14, flexDirection: "row", alignItems: "center", gap: 11 },
  familyOptionCopy: { flex: 1, gap: 2 },
  familyOptionTitle: { fontSize: 15, lineHeight: 21, fontWeight: "900" },
  familyOptionMeta: { fontSize: 12, lineHeight: 18, fontWeight: "600" },
  boundaryCard: { borderRadius: 16, backgroundColor: "#F7F8FA", padding: 14, gap: 8 },
  boundaryCardTitle: { fontSize: 15, lineHeight: 21, fontWeight: "900" },
  boundaryCardDetail: { fontSize: 12, lineHeight: 18, fontWeight: "600" },
  pressed: { opacity: 0.82, transform: [{ scale: 0.985 }] },
});
