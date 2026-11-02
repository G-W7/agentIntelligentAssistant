import { Bot, User } from "lucide-react";

import { Markdown } from "@/components/chat/markdown";
import { RouteBadge } from "@/components/chat/route-badge";
import { SourcesList } from "@/components/chat/sources-list";
import { cn } from "@/lib/utils";
import { formatTime } from "@/lib/format";
import type { ChatMessage } from "@/lib/types";

export function BotAvatar({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-linear-to-br from-indigo-500 to-violet-600 text-white shadow-sm",
        className,
      )}
      aria-hidden
    >
      <Bot className="size-4" />
    </div>
  );
}

export function ChatMessageItem({
  message,
  fileNames,
}: {
  message: ChatMessage;
  fileNames: Map<string, string>;
}) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end gap-2.5">
        <div className="flex min-w-0 max-w-[85%] flex-col items-end">
          <div className="rounded-2xl rounded-br-md bg-linear-to-br from-indigo-600 to-violet-600 px-4 py-2.5 text-white shadow-sm">
            <p className="whitespace-pre-wrap break-words text-sm leading-6 [overflow-wrap:anywhere]">
              {message.content}
            </p>
          </div>
          {message.createdAt ? (
            <time
              dateTime={message.createdAt}
              className="mt-1 text-[10px] text-muted-foreground"
            >
              {formatTime(message.createdAt)}
            </time>
          ) : null}
        </div>
        <div
          className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-muted text-muted-foreground ring-1 ring-border/60"
          aria-hidden
        >
          <User className="size-3.5" />
        </div>
      </div>
    );
  }

  const route = message.metadata?.route;
  const reason = message.metadata?.route_reason;
  const sources = message.metadata?.sources ?? [];
  const time = formatTime(message.createdAt);

  return (
    <div className="flex gap-2.5">
      <BotAvatar />
      <div className="min-w-0 flex-1">
        <div className="rounded-2xl rounded-tl-md border border-border/60 bg-card px-4 py-3 shadow-xs">
          {route || reason || time ? (
            <div className="mb-2 flex flex-wrap items-center gap-2">
              {route ? <RouteBadge route={route} /> : null}
              {reason ? (
                <span
                  className="line-clamp-1 min-w-0 flex-1 text-[11px] text-muted-foreground"
                  title={reason}
                >
                  {reason}
                </span>
              ) : null}
              {time ? (
                <time
                  dateTime={message.createdAt ?? undefined}
                  className="ml-auto shrink-0 text-[10px] text-muted-foreground"
                >
                  {time}
                </time>
              ) : null}
            </div>
          ) : null}

          {message.content.trim() ? (
            <Markdown content={message.content} />
          ) : (
            <p className="text-sm text-muted-foreground">Agent 未返回内容。</p>
          )}

          {sources.length > 0 ? (
            <SourcesList sources={sources} fileNames={fileNames} />
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function PendingMessage() {
  return (
    <div className="flex gap-2.5">
      <BotAvatar />
      <div className="rounded-2xl rounded-tl-md border border-border/60 bg-card px-4 py-3 shadow-xs">
        <div className="flex items-center gap-1">
          <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.3s]" />
          <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.15s]" />
          <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground" />
          <span className="ml-2 text-xs text-muted-foreground">
            Agent 正在思考…
          </span>
        </div>
      </div>
    </div>
  );
}
