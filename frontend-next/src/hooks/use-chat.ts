"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api, getErrorMessage } from "@/lib/api";
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
 * - 发送时先把用户消息 + 空的助手占位消息一起乐观写入缓存，随后按
 *   SSE 事件增量更新占位消息的 content / metadata；
 * - 请求失败保留用户消息与已收到的部分回答，并给出错误提示。
 */
export function useChat(sessionId: string) {
  const queryClient = useQueryClient();
  const inFlight = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
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

  // 组件卸载时中断进行中的流，避免内存泄漏与状态错位
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      abortRef.current = null;
    };
  }, []);

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
      const assistantId = localId("local-assistant");
      const assistantPlaceholder: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        metadata: null,
        createdAt: new Date().toISOString(),
        streaming: true,
      };
      queryClient.setQueryData<ChatMessage[]>(targetKey, (current) => [
        ...(current ?? []),
        userMessage,
        assistantPlaceholder,
      ]);

      const patchAssistant = (patch: (msg: ChatMessage) => ChatMessage) => {
        queryClient.setQueryData<ChatMessage[]>(targetKey, (current) =>
          (current ?? []).map((item) =>
            item.id === assistantId ? patch(item) : item,
          ),
        );
      };

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        for await (const event of api.chatStream(
          { message, session_id: targetSession },
          controller.signal,
        )) {
          switch (event.type) {
            case "start":
              // 目前无需处理，保留钩子以便未来展示会话切换等状态
              break;
            case "route":
              patchAssistant((msg) => ({
                ...msg,
                metadata: {
                  ...(msg.metadata ?? {}),
                  route: event.route,
                  route_reason: event.route_reason,
                },
              }));
              break;
            case "delta":
              patchAssistant((msg) => ({
                ...msg,
                content: msg.content + event.content,
              }));
              break;
            case "sources":
              patchAssistant((msg) => ({
                ...msg,
                metadata: {
                  ...(msg.metadata ?? {}),
                  sources: normalizeSources(event.sources) ?? [],
                },
              }));
              break;
            case "done":
              patchAssistant((msg) => ({
                ...msg,
                content: event.answer || msg.content,
                metadata: {
                  route: event.route,
                  route_reason: event.route_reason,
                  sources: normalizeSources(event.sources) ?? [],
                },
                streaming: false,
              }));
              break;
            case "error":
              throw new ApiError(event.message);
          }
        }
        // 保险：若因异常路径未收到 done，也要清除流式标记
        patchAssistant((msg) =>
          msg.streaming ? { ...msg, streaming: false } : msg,
        );
        void queryClient.invalidateQueries({ queryKey: queryKeys.sessions });
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          // 主动取消不视为错误，仅清除流式标记
          patchAssistant((msg) => ({ ...msg, streaming: false }));
        } else {
          // 后端可能已经保存了用户消息；保留乐观消息，刷新历史可回到服务端真实状态。
          patchAssistant((msg) => ({ ...msg, streaming: false }));
          setSendError({
            sessionId: targetSession,
            message: getErrorMessage(error),
          });
        }
      } finally {
        inFlight.current = false;
        setPendingSessionId(null);
        abortRef.current = null;
      }
    },
    [queryClient, sessionId],
  );

  const isSending = pendingSessionId !== null;

  return {
    messages: historyQuery.data ?? [],
    isLoading: historyQuery.isLoading,
    isFetching: historyQuery.isFetching,
    historyError: historyQuery.isError
      ? getErrorMessage(historyQuery.error)
      : null,
    isSending,
    isSendingHere: isSending && pendingSessionId === sessionId,
    sendError: sendError?.sessionId === sessionId ? sendError.message : null,
    send,
    dismissSendError: () => setSendError(null),
    reload: historyQuery.refetch,
    cancel: () => {
      abortRef.current?.abort();
    },
  };
}
