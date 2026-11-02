"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import { Bot } from "lucide-react";

import { ThemeToggle } from "@/components/theme-toggle";
import { getErrorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { HealthResponse } from "@/lib/types";

function BackendStatus({
  query,
}: {
  query: UseQueryResult<HealthResponse, Error>;
}) {
  let label = "检测中";
  let className = "border-border bg-muted/40 text-muted-foreground";
  let dotClassName = "bg-muted-foreground animate-pulse";
  let title = "正在检测后端服务";

  if (query.isError) {
    label = "后端离线";
    className = "border-destructive/20 bg-destructive/10 text-destructive";
    dotClassName = "bg-destructive";
    title = getErrorMessage(query.error);
  } else if (query.data) {
    if (query.data.status === "ok") {
      label = "服务正常";
      className =
        "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
      dotClassName = "bg-emerald-500";
      title = "PostgreSQL 与 Milvus 均正常";
    } else {
      label = "部分降级";
      className =
        "border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-300";
      dotClassName = "bg-amber-500";
      title = `PostgreSQL ${query.data.postgres ? "正常" : "不可用"} · Milvus ${query.data.milvus ? "正常" : "不可用"}`;
    }
  }

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium",
        className,
      )}
      title={title}
    >
      <span className={cn("size-1.5 rounded-full", dotClassName)} />
      {label}
    </span>
  );
}

export function AppHeader({
  healthQuery,
}: {
  healthQuery: UseQueryResult<HealthResponse, Error>;
}) {
  return (
    <header className="sticky top-0 z-40 border-b border-border/60 bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto flex h-14 w-full max-w-[1440px] items-center gap-3 px-3 sm:px-4 lg:px-6">
        <div className="grid size-9 shrink-0 place-items-center rounded-xl bg-linear-to-br from-indigo-500 to-violet-600 text-white shadow-sm shadow-indigo-500/20">
          <Bot className="size-5" />
        </div>

        <div className="min-w-0">
          <h1 className="truncate text-sm font-semibold leading-tight tracking-tight sm:text-base">
            Agent 智能助手
          </h1>
          <p className="hidden truncate text-[11px] text-muted-foreground sm:block">
            多 Agent 协作 · 本地知识库 RAG · Tavily 联网搜索
          </p>
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-1.5">
          <BackendStatus query={healthQuery} />
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
