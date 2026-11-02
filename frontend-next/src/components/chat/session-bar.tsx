"use client";

import { History, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function SessionBar({
  sessionId,
  onReload,
  isReloading,
  disableActions,
}: {
  sessionId: string;
  onReload: () => void;
  isReloading: boolean;
  disableActions: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 border-b border-border/60 bg-card/40 px-3 py-2.5 sm:px-4">
      <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <History className="size-3.5" />
        会话
      </span>

      <span className="truncate font-mono text-xs text-foreground" title={sessionId}>
        {sessionId}
      </span>

      <div className="ml-auto flex items-center gap-1">
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={onReload}
          disabled={isReloading || disableActions}
          title="刷新会话历史"
          aria-label="刷新会话历史"
        >
          <RefreshCw className={cn("size-4", isReloading && "animate-spin")} />
        </Button>
      </div>
    </div>
  );
}
