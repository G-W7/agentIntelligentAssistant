"use client";

import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowDown,
  RefreshCw,
  Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ChatMessageItem,
  PendingMessage,
} from "@/components/chat/chat-message";
import {
  KNOWLEDGE_SUGGESTION,
  SUGGESTIONS,
} from "@/lib/constants";
import type { ChatMessage } from "@/lib/types";

function MessageSkeleton() {
  return (
    <div className="space-y-5" aria-hidden>
      <div className="flex justify-end">
        <Skeleton className="h-10 w-2/5 rounded-2xl" />
      </div>
      <div className="flex gap-2.5">
        <Skeleton className="size-7 shrink-0 rounded-full" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-4/5" />
          <Skeleton className="h-4 w-3/5" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      </div>
    </div>
  );
}

function Welcome({
  onSuggestion,
  hasFiles,
}: {
  onSuggestion: (text: string) => void;
  hasFiles: boolean;
}) {
  const suggestions = hasFiles
    ? [SUGGESTIONS[0], KNOWLEDGE_SUGGESTION, SUGGESTIONS[1]]
    : [...SUGGESTIONS];

  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4 py-10 text-center">
      <div className="grid size-14 place-items-center rounded-2xl bg-linear-to-br from-indigo-500 to-violet-600 text-white shadow-lg shadow-indigo-500/20">
        <Sparkles className="size-7" />
      </div>
      <h2 className="mt-4 text-lg font-semibold tracking-tight">
        今天想了解什么？
      </h2>
      <p className="mt-1.5 max-w-md text-sm leading-6 text-muted-foreground">
        我会自动判断问题该走知识库检索、联网搜索还是直接对话，并在回答下方附上参考来源。
      </p>
      <div className="mt-6 grid w-full max-w-md gap-2">
        {suggestions.map((text) => (
          <button
            key={text}
            type="button"
            onClick={() => onSuggestion(text)}
            className="group flex items-center gap-2.5 rounded-xl border border-border/60 bg-card/70 px-3.5 py-2.5 text-left text-sm transition-colors hover:border-border hover:bg-muted/60"
          >
            <Sparkles className="size-3.5 shrink-0 text-muted-foreground transition-colors group-hover:text-indigo-500" />
            <span className="flex-1">{text}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export function ChatMessages({
  messages,
  fileNames,
  isLoading,
  historyError,
  isSendingHere,
  onRetry,
  onSuggestion,
  hasFiles,
}: {
  messages: ChatMessage[];
  fileNames: Map<string, string>;
  isLoading: boolean;
  historyError: string | null;
  isSendingHere: boolean;
  onRetry: () => void;
  onSuggestion: (text: string) => void;
  hasFiles: boolean;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const previousCount = useRef(0);
  const [atBottom, setAtBottom] = useState(true);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;

    const grew = messages.length > previousCount.current;
    previousCount.current = messages.length;

    if (atBottom && grew) {
      element.scrollTo({ top: element.scrollHeight, behavior: "smooth" });
    }
  }, [messages.length, atBottom]);

  // 展开来源、图片加载等会让内容高度变化，需要重新判断是否仍在底部。
  useEffect(() => {
    const content = contentRef.current;
    const element = scrollRef.current;
    if (!content || !element) return;

    const observer = new ResizeObserver(() => {
      const distance =
        element.scrollHeight - element.scrollTop - element.clientHeight;
      setAtBottom(distance < 32);
    });
    observer.observe(content);
    return () => observer.disconnect();
  }, []);

  function handleScroll() {
    const element = scrollRef.current;
    if (!element) return;
    const distance =
      element.scrollHeight - element.scrollTop - element.clientHeight;
    setAtBottom(distance < 32);
  }

  function scrollToBottom() {
    const element = scrollRef.current;
    if (!element) return;
    element.scrollTo({ top: element.scrollHeight, behavior: "smooth" });
    setAtBottom(true);
  }

  const showWelcome = !isLoading && !historyError && messages.length === 0;

  return (
    <div className="relative h-full">
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="scrollbar-thin h-full overflow-y-auto overscroll-contain px-3 py-4 sm:px-5"
      >
        <div
          ref={contentRef}
          className="mx-auto flex min-h-full w-full max-w-3xl flex-col gap-5"
        >
          {isLoading ? (
            <MessageSkeleton />
          ) : historyError && messages.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
              <AlertTriangle className="size-8 text-destructive" />
              <p className="text-sm font-medium">加载会话历史失败</p>
              <p className="max-w-md break-words text-xs leading-5 text-muted-foreground">
                {historyError}
              </p>
              <Button variant="outline" size="sm" onClick={onRetry}>
                <RefreshCw className="size-3.5" />
                重试
              </Button>
            </div>
          ) : showWelcome ? (
            <Welcome onSuggestion={onSuggestion} hasFiles={hasFiles} />
          ) : (
            <>
              {messages.map((message) => (
                <ChatMessageItem
                  key={message.id}
                  message={message}
                  fileNames={fileNames}
                />
              ))}
              {isSendingHere ? <PendingMessage /> : null}
            </>
          )}
        </div>
      </div>

      {!atBottom && !isLoading ? (
        <Button
          type="button"
          variant="outline"
          size="icon-sm"
          onClick={scrollToBottom}
          aria-label="滚动到底部"
          title="滚动到底部"
          className="absolute right-4 bottom-4 rounded-full bg-background/90 shadow-md backdrop-blur"
        >
          <ArrowDown className="size-4" />
        </Button>
      ) : null}
    </div>
  );
}
