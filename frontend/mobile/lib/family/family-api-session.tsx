import * as SecureStore from "expo-secure-store";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type PropsWithChildren } from "react";
import { Platform } from "react-native";

import { familyApi, FamilyApiError, type FamilyContextSummary } from "@/lib/family/family-api-client";

const TOKEN_KEY = "family-api-account-token";
const FAMILY_KEY = "family-api-selected-family";
const DEV_EXTERNAL_REF = process.env.EXPO_PUBLIC_FAMILY_DEV_EXTERNAL_REF?.trim() || "family-ai-mobile-dev";
const AUTO_DEV_SESSION = process.env.EXPO_PUBLIC_FAMILY_DEV_AUTO_SESSION === "true";

export type FamilyApiSessionStatus = "loading" | "local_synthetic" | "connected" | "family_selection" | "no_family" | "error";

interface FamilyApiSessionContextValue {
  configured: boolean;
  status: FamilyApiSessionStatus;
  token: string | null;
  accountId: string | null;
  contexts: FamilyContextSummary[];
  selectedFamily: FamilyContextSummary | null;
  error: FamilyApiError | null;
  usingSyntheticFallback: boolean;
  connectDevSession(): Promise<void>;
  selectFamily(familyId: string): Promise<void>;
  refresh(): Promise<void>;
  disconnect(): Promise<void>;
}

const FamilyApiSessionContext = createContext<FamilyApiSessionContextValue | null>(null);

export function FamilyApiSessionProvider({ children }: PropsWithChildren) {
  const [status, setStatus] = useState<FamilyApiSessionStatus>("loading");
  const [token, setToken] = useState<string | null>(null);
  const [accountId, setAccountId] = useState<string | null>(null);
  const [contexts, setContexts] = useState<FamilyContextSummary[]>([]);
  const [selectedFamily, setSelectedFamily] = useState<FamilyContextSummary | null>(null);
  const [error, setError] = useState<FamilyApiError | null>(null);

  const loadContexts = useCallback(async (activeToken: string) => {
    const response = await familyApi.getContexts(activeToken);
    const storedFamilyId = await readStorage(FAMILY_KEY);
    const storedContext = response.contexts.find((item) => item.family_id === storedFamilyId) ?? null;
    const nextSelected = storedContext ?? (response.contexts.length === 1 ? response.contexts[0] : null);
    setAccountId(response.account_id);
    setContexts(response.contexts);
    setSelectedFamily(nextSelected);
    if (nextSelected) {
      await writeStorage(FAMILY_KEY, nextSelected.family_id);
      setStatus("connected");
    } else {
      setStatus(response.contexts.length === 0 ? "no_family" : "family_selection");
    }
  }, []);

  const connectDevSession = useCallback(async () => {
    if (!familyApi.configured) {
      setStatus("local_synthetic");
      return;
    }
    try {
      setStatus("loading");
      setError(null);
      const session = await familyApi.issueDevAccountSession(DEV_EXTERNAL_REF);
      await writeStorage(TOKEN_KEY, session.token);
      setToken(session.token);
      await loadContexts(session.token);
    } catch (cause) {
      setError(asFamilyApiError(cause));
      setStatus("error");
    }
  }, [loadContexts]);

  const refresh = useCallback(async () => {
    if (!familyApi.configured) {
      setStatus("local_synthetic");
      return;
    }
    const storedToken = token ?? await readStorage(TOKEN_KEY);
    if (!storedToken) {
      if (AUTO_DEV_SESSION) {
        await connectDevSession();
      } else {
        setStatus("local_synthetic");
      }
      return;
    }
    try {
      setStatus("loading");
      setError(null);
      await familyApi.getAccount(storedToken);
      setToken(storedToken);
      await loadContexts(storedToken);
    } catch (cause) {
      const nextError = asFamilyApiError(cause);
      setError(nextError);
      if (nextError.status === 401) {
        await removeStorage(TOKEN_KEY);
        setToken(null);
      }
      setStatus("error");
    }
  }, [connectDevSession, loadContexts, token]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const selectFamily = useCallback(async (familyId: string) => {
    const context = contexts.find((item) => item.family_id === familyId);
    if (!context) throw new Error("家庭上下文不存在或已失效");
    await writeStorage(FAMILY_KEY, familyId);
    setSelectedFamily(context);
    setStatus("connected");
  }, [contexts]);

  const disconnect = useCallback(async () => {
    const activeToken = token;
    if (activeToken && familyApi.configured) {
      await familyApi.revokeSession(activeToken).catch(() => undefined);
    }
    await Promise.all([removeStorage(TOKEN_KEY), removeStorage(FAMILY_KEY)]);
    setToken(null);
    setAccountId(null);
    setContexts([]);
    setSelectedFamily(null);
    setError(null);
    setStatus(familyApi.configured ? "local_synthetic" : "local_synthetic");
  }, [token]);

  const value = useMemo<FamilyApiSessionContextValue>(() => ({
    configured: familyApi.configured,
    status,
    token,
    accountId,
    contexts,
    selectedFamily,
    error,
    usingSyntheticFallback: status !== "connected",
    connectDevSession,
    selectFamily,
    refresh,
    disconnect,
  }), [accountId, connectDevSession, contexts, disconnect, error, refresh, selectFamily, selectedFamily, status, token]);

  return <FamilyApiSessionContext.Provider value={value}>{children}</FamilyApiSessionContext.Provider>;
}

export function useFamilyApiSession() {
  const value = useContext(FamilyApiSessionContext);
  if (!value) throw new Error("useFamilyApiSession must be used within FamilyApiSessionProvider");
  return value;
}

function asFamilyApiError(cause: unknown) {
  return cause instanceof FamilyApiError
    ? cause
    : new FamilyApiError(cause instanceof Error ? cause.message : "Family API 会话错误", 0, "FAMILY_API_SESSION_ERROR", null);
}

async function readStorage(key: string) {
  if (Platform.OS === "web") return typeof window === "undefined" ? null : window.localStorage.getItem(key);
  return SecureStore.getItemAsync(key);
}

async function writeStorage(key: string, value: string) {
  if (Platform.OS === "web") {
    if (typeof window !== "undefined") window.localStorage.setItem(key, value);
    return;
  }
  await SecureStore.setItemAsync(key, value);
}

async function removeStorage(key: string) {
  if (Platform.OS === "web") {
    if (typeof window !== "undefined") window.localStorage.removeItem(key);
    return;
  }
  await SecureStore.deleteItemAsync(key);
}
