"use client";

import { AlertTriangle, X } from "lucide-react";

import { ChatComposer } from "@/components/chat/chat-composer";
import { ChatMessages } from "@/components/chat/chat-messages";
import { SessionBar } from "@/components/chat/session-bar";
import { useChat } from "@/hooks/use-chat";

export function ChatPanel({
  sessionId,
  fileNames,
  hasFiles,
}: {
  sessionId: string;
  fileNames: Map<string, string>;
  hasFiles: boolean;
}) {
  const chat = useChat(sessionId);

  return (
    <section className="flex h-[72vh] min-h-[520px] flex-col overflow-hidden rounded-2xl bg-card shadow-sm ring-1 ring-foreground/10 lg:h-[calc(100dvh-8.5rem)] lg:min-h-[560px]">
      <SessionBar
        sessionId={sessionId}
        onReload={() => {
          void chat.reload();
        }}
        isReloading={chat.isFetching}
        disableActions={chat.isSending}
      />

      <div className="min-h-0 flex-1">
        <ChatMessages
          key={sessionId}
          messages={chat.messages}
          fileNames={fileNames}
          isLoading={chat.isLoading}
          historyError={chat.historyError}
          isSendingHere={chat.isSendingHere}
          onRetry={() => {
            void chat.reload();
          }}
          onSuggestion={(text) => {
            void chat.send(text);
          }}
          hasFiles={hasFiles}
        />
      </div>

      {chat.sendError ? (
        <div className="flex items-start gap-2 border-t border-destructive/20 bg-destructive/5 px-3 py-2 text-xs text-destructive sm:px-4">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
          <p className="min-w-0 flex-1 break-words leading-5">
            {chat.sendError}
          </p>
          <button
            type="button"
            onClick={chat.dismissSendError}
            className="shrink-0 rounded p-0.5 transition-colors hover:bg-destructive/10"
            aria-label="关闭错误提示"
          >
            <X className="size-3.5" />
          </button>
        </div>
      ) : null}

      <ChatComposer
        onSend={(message) => {
          void chat.send(message);
        }}
        disabled={chat.isLoading}
        isSending={chat.isSending}
      />
    </section>
  );
}
