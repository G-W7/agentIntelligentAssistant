"use client";

import { useCallback, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, getErrorMessage } from "@/lib/api";
import { queryKeys } from "@/hooks/queries";
import type {
  ChatMessage,
  HistoryItem,
  MessageMetadata,
  Route,
  SourceItem,
} from "@/lib/types";

const ROUTES: readonly Route[] = ["rag", "chat", "search"];

function isRoute(value: unknown): value is Route {
  return typeof value === "string" && ROUTES.includes(value as Route);
}

function normalizeSources(value: unknown): SourceItem[] | undefined {
  if (!Array.isArray(value)) return undefined;
  return value.flatMap((item): SourceItem[] => {
    if (!item || typeof item !== "object") return [];
    const source = item as Record<string, unknown>;
    if (source.kind !== "knowledge" && source.kind !== "web") return [];
    return [
      {
        kind: source.kind,
        title: typeof source.title === "string" ? source.title : null,
        url: typeof source.url === "string" ? source.url : null,
        file_id: typeof source.file_id === "string" ? source.file_id : null,
        page: typeof source.page === "number" ? source.page : null,
        index: typeof source.index === "number" ? source.index : null,
        score: typeof source.score === "number" ? source.score : 0,
        content: typeof source.content === "string" ? source.content : "",
      },
    ];
  });
}

/** 历史元数据来自数据库 JSONB，这里做一层防御性归一化。 */
function normalizeMetadata(metadata: MessageMetadata | null): MessageMetadata | null {
  if (!metadata || typeof metadata !== "object") return null;
  const record = metadata as Record<string, unknown>;
  const normalized: MessageMetadata = {};

  if (isRoute(record.route)) normalized.route = record.route;
  if (typeof record.route_reason === "string") {
    normalized.route_reason = record.route_reason;
  }

  const sources = normalizeSources(record.sources);
  if (sources) normalized.sources = sources;

  return Object.keys(normalized).length > 0 ? normalized : null;
}

function toChatMessage(item: HistoryItem): ChatMessage {
  return {
    id: `history-${item.id}`,
    role: item.role,
    content: item.content,
    metadata: normalizeMetadata(item.metadata),
    createdAt: item.created_at,
  };
}

function localId(prefix: string): string {
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2);
  return `${prefix}-${random}`;
}

/**
 * 会话消息状态：
 * - 历史消息由 React Query 缓存管理；
 * - 发送时先把用户消息乐观写入缓存，成功后追加助手消息；
 * - 请求失败保留用户消息并给出错误提示。
 */
export function useChat(sessionId: string) {
  const queryClient = useQueryClient();
  const inFlight = useRef(false);
  // 错误与发起请求的会话绑定，切换会话后自然不再展示。
  const [sendError, setSendError] = useState<{
    sessionId: string;
    message: string;
  } | null>(null);
  const [pendingSessionId, setPendingSessionId] = useState<string | null>(null);

  const historyKey = queryKeys.history(sessionId);

  const historyQuery = useQuery({
    queryKey: historyKey,
    queryFn: ({ signal }) =>
      api.history(sessionId, 200, signal).then((rows) => rows.map(toChatMessage)),
    refetchOnWindowFocus: false,
    retry: 1,
    staleTime: 10_000,
  });

  const mutation = useMutation({
    mutationFn: (variables: { message: string; sessionId: string }) =>
      api.chat({ message: variables.message, session_id: variables.sessionId }),
  });

  const send = useCallback(
    async (raw: string) => {
      const message = raw.trim();
      if (!message || inFlight.current) return;

      const targetSession = sessionId;
      const targetKey = queryKeys.history(targetSession);
      inFlight.current = true;
      setSendError(null);
      setPendingSessionId(targetSession);

      const userMessage: ChatMessage = {
        id: localId("local-user"),
        role: "user",
        content: message,
        metadata: null,
        createdAt: new Date().toISOString(),
      };
      queryClient.setQueryData<ChatMessage[]>(targetKey, (current) => [
        ...(current ?? []),
        userMessage,
      ]);

      try {
        const response = await mutation.mutateAsync({
          message,
          sessionId: targetSession,
        });
        const assistantMessage: ChatMessage = {
          id: localId("local-assistant"),
          role: "assistant",
          content: response.answer,
          metadata: {
            route: response.route,
            route_reason: response.route_reason,
            sources: response.sources,
          },
          createdAt: new Date().toISOString(),
        };
        queryClient.setQueryData<ChatMessage[]>(targetKey, (current) => [
          ...(current ?? []),
          assistantMessage,
        ]);
      } catch (error) {
        // 后端可能已经保存了用户消息；保留乐观消息，刷新历史可回到服务端真实状态。
        setSendError({ sessionId: targetSession, message: getErrorMessage(error) });
      } finally {
        inFlight.current = false;
        setPendingSessionId(null);
      }
    },
    [mutation, queryClient, sessionId],
  );

  return {
    messages: historyQuery.data ?? [],
    isLoading: historyQuery.isLoading,
    isFetching: historyQuery.isFetching,
    historyError: historyQuery.isError
      ? getErrorMessage(historyQuery.error)
      : null,
    isSending: mutation.isPending,
    isSendingHere: mutation.isPending && pendingSessionId === sessionId,
    sendError: sendError?.sessionId === sessionId ? sendError.message : null,
    send,
    dismissSendError: () => setSendError(null),
    reload: historyQuery.refetch,
  };
}
