"use client";

import { useState } from "react";
import { History, Plus, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MAX_SESSION_LENGTH } from "@/lib/constants";
import { cn } from "@/lib/utils";
import { createSessionId, useSessionStore } from "@/stores/session-store";

/**
 * 输入框以 sessionId 作为 key 挂载：切换或新建会话时组件重建，
 * draft 自动跟随当前会话，无需在 effect 中同步 prop 到 state。
 */
function SessionForm({
  sessionId,
  onSwitch,
}: {
  sessionId: string;
  onSwitch: (sessionId: string) => void;
}) {
  const [draft, setDraft] = useState(sessionId);
  const canSwitch = draft.trim().length > 0 && draft.trim() !== sessionId;

  return (
    <form
      className="flex items-center gap-1.5"
      onSubmit={(event) => {
        event.preventDefault();
        if (canSwitch) onSwitch(draft.trim());
      }}
    >
      <Input
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        maxLength={MAX_SESSION_LENGTH}
        spellCheck={false}
        aria-label="会话 ID"
        placeholder="会话 ID"
        className="h-8 w-40 font-mono text-xs sm:w-52"
      />
      <Button type="submit" variant="outline" size="sm" disabled={!canSwitch}>
        切换
      </Button>
    </form>
  );
}

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
  const setSessionId = useSessionStore((state) => state.setSessionId);

  function startNewSession() {
    setSessionId(createSessionId());
  }

  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5 border-b border-border/60 bg-card/40 px-3 py-2.5 sm:px-4">
      <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
        <History className="size-3.5" />
        会话
      </span>

      <SessionForm key={sessionId} sessionId={sessionId} onSwitch={setSessionId} />

      <div className="ml-auto flex items-center gap-1">
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={startNewSession}
          disabled={disableActions}
          title="新建会话"
          aria-label="新建会话"
        >
          <Plus className="size-4" />
        </Button>
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
