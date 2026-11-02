"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import { Activity, AlertTriangle, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { getErrorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { HealthResponse } from "@/lib/types";

function StatusRow({ label, ok }: { label: string; ok: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs">
      <span className="flex items-center gap-2">
        <span
          className={cn(
            "size-2 rounded-full",
            ok ? "bg-emerald-500" : "bg-destructive",
          )}
        />
        {label}
      </span>
      <span
        className={
          ok
            ? "font-medium text-emerald-600 dark:text-emerald-400"
            : "font-medium text-destructive"
        }
      >
        {ok ? "正常" : "不可用"}
      </span>
    </div>
  );
}

function StatTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border/60 bg-muted/25 px-2.5 py-2">
      <p className="text-[10px] text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-sm font-semibold tabular-nums">
        {value.toLocaleString("zh-CN")}
      </p>
    </div>
  );
}

export function ServiceStatus({
  query,
}: {
  query: UseQueryResult<HealthResponse, Error>;
}) {
  return (
    <Card className="gap-0 py-0">
      <CardHeader className="flex flex-row items-center justify-between gap-2 border-b border-border/60 px-4 py-3">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Activity className="size-4 text-muted-foreground" />
          服务状态
        </CardTitle>
        <Button
          type="button"
          variant="ghost"
          size="icon-xs"
          onClick={() => {
            void query.refetch();
          }}
          disabled={query.isFetching}
          aria-label="刷新服务状态"
          title="刷新服务状态"
        >
          <RefreshCw
            className={cn("size-3.5", query.isFetching && "animate-spin")}
          />
        </Button>
      </CardHeader>

      <CardContent className="space-y-3 px-4 py-3">
        {query.isPending ? (
          <div className="space-y-2.5" aria-hidden>
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
            <div className="grid grid-cols-2 gap-2 pt-1">
              <Skeleton className="h-12 rounded-lg" />
              <Skeleton className="h-12 rounded-lg" />
            </div>
          </div>
        ) : query.isError ? (
          <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-2.5">
            <p className="flex items-center gap-1.5 text-xs font-medium text-destructive">
              <AlertTriangle className="size-3.5" />
              后端不可达
            </p>
            <p className="mt-1 break-words text-[10px] leading-4 text-muted-foreground">
              {getErrorMessage(query.error)}
            </p>
          </div>
        ) : (
          <>
            <div className="space-y-2">
              <StatusRow label="PostgreSQL" ok={query.data.postgres} />
              <StatusRow label="Milvus" ok={query.data.milvus} />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <StatTile label="向量切片" value={query.data.milvus_vectors} />
              <StatTile label="知识库文件" value={query.data.knowledge_files} />
            </div>

            <p className="text-[10px] leading-4 text-muted-foreground">
              {query.data.status === "ok"
                ? "所有依赖服务运行正常，每 30 秒自动刷新。"
                : "部分依赖服务不可用，检索或历史功能可能受限。"}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
