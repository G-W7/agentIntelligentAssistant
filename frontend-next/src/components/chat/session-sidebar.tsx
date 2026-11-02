"use client";

import { useMemo, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, MessageSquare, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { queryKeys, useSessionsQuery } from "@/hooks/queries";
import { api, getErrorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { SessionItem } from "@/lib/types";
import { createSessionId, useSessionStore } from "@/stores/session-store";

function formatTime(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  if (sameDay) {
    return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
}

export function SessionSidebar({
  sessionId,
  disabled,
}: {
  sessionId: string;
  disabled: boolean;
}) {
  const queryClient = useQueryClient();
  const setSessionId = useSessionStore((state) => state.setSessionId);
  const sessionsQuery = useSessionsQuery();

  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const deleteMutation = useMutation({
    mutationFn: (targetSessionId: string) => api.deleteSession(targetSessionId),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.sessions });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.history(data.session_id),
      });
      if (data.session_id === sessionId) {
        setSessionId(createSessionId());
      }
      setDeleteTarget(null);
      setDeleteError(null);
    },
    onError: (error) => {
      setDeleteError(getErrorMessage(error));
    },
  });

  const sessions = useMemo(() => {
    const list = [...(sessionsQuery.data ?? [])];
    if (!list.some((item) => item.session_id === sessionId)) {
      list.unshift({
        session_id: sessionId,
        last_message_at: new Date().toISOString(),
        message_count: 0,
        preview: "",
      });
    }
    return list;
  }, [sessionsQuery.data, sessionId]);

  function closeDialog() {
    if (deleteMutation.isPending) return;
    setDeleteTarget(null);
    setDeleteError(null);
  }

  return (
    <>
      <aside className="flex h-[72vh] min-h-[520px] flex-col overflow-hidden rounded-2xl bg-card shadow-sm ring-1 ring-foreground/10 lg:h-[calc(100dvh-8.5rem)] lg:min-h-[560px]">
        <div className="flex items-center justify-between gap-2 border-b border-border/60 px-3 py-2.5">
          <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <MessageSquare className="size-3.5" />
            历史会话
          </span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setSessionId(createSessionId())}
            disabled={disabled}
            title="新建会话"
          >
            <Plus className="size-3.5" />
            新建
          </Button>
        </div>

        <ScrollArea className="min-h-0 flex-1">
          <div className="flex flex-col gap-1 p-2">
            {sessionsQuery.isLoading
              ? Array.from({ length: 6 }).map((_, index) => (
                  <Skeleton key={index} className="h-14 rounded-lg" />
                ))
              : sessions.map((item: SessionItem) => {
                  const active = item.session_id === sessionId;
                  return (
                    <div
                      key={item.session_id}
                      className={cn(
                        "group relative flex flex-col gap-0.5 rounded-lg px-2.5 py-2 transition-colors",
                        active
                          ? "bg-primary/10 ring-1 ring-primary/30"
                          : "hover:bg-muted/60",
                      )}
                    >
                      <button
                        type="button"
                        onClick={() => setSessionId(item.session_id)}
                        disabled={disabled}
                        aria-current={active ? "true" : undefined}
                        className="flex w-full flex-col gap-0.5 text-left"
                      >
                        <span className="flex items-center justify-between gap-2">
                          <span
                            className={cn(
                              "truncate font-mono text-xs",
                              active ? "text-primary" : "text-foreground",
                            )}
                          >
                            {item.session_id}
                          </span>
                          <span className="shrink-0 text-[10px] text-muted-foreground">
                            {formatTime(item.last_message_at)}
                          </span>
                        </span>
                        <span className="line-clamp-1 pr-6 text-[11px] text-muted-foreground">
                          {item.preview || "暂无消息"}
                        </span>
                      </button>

                      {item.message_count > 0 ? (
                        <button
                          type="button"
                          onClick={() => {
                            setDeleteTarget(item.session_id);
                            setDeleteError(null);
                          }}
                          disabled={deleteMutation.isPending}
                          aria-label={`删除会话 ${item.session_id}`}
                          title="删除会话"
                          className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100"
                        >
                          <Trash2 className="size-3.5" />
                        </button>
                      ) : null}
                    </div>
                  );
                })}
            {!sessionsQuery.isLoading && sessions.length === 0 ? (
              <p className="px-2 py-6 text-center text-xs text-muted-foreground">
                暂无历史会话
              </p>
            ) : null}
          </div>
        </ScrollArea>
      </aside>

      <Dialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) closeDialog();
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除会话</DialogTitle>
            <DialogDescription>
              将永久删除会话{" "}
              <span className="font-mono font-medium text-foreground">
                {deleteTarget}
              </span>{" "}
              的全部聊天记录，此操作不可撤销。
            </DialogDescription>
          </DialogHeader>

          {deleteError ? (
            <p className="break-words rounded-md bg-destructive/10 px-2.5 py-1.5 text-xs text-destructive">
              {deleteError}
            </p>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={closeDialog}
              disabled={deleteMutation.isPending}
            >
              取消
            </Button>
            <Button
              type="button"
              variant="destructive"
              onClick={() => {
                if (deleteTarget) deleteMutation.mutate(deleteTarget);
              }}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Trash2 className="size-4" />
              )}
              确认删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}