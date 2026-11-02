"use client";

import { useMemo } from "react";

import { AppHeader } from "@/components/app-header";
import { ChatPanel } from "@/components/chat/chat-panel";
import { KnowledgePanel } from "@/components/knowledge/knowledge-panel";
import { ServiceStatus } from "@/components/service-status";
import { Skeleton } from "@/components/ui/skeleton";
import { useFilesQuery, useHealthQuery } from "@/hooks/queries";
import { useMounted } from "@/hooks/use-mounted";
import { useSessionStore } from "@/stores/session-store";

function DashboardSkeleton() {
  return (
    <div className="flex flex-1 flex-col">
      <header className="border-b border-border/60">
        <div className="mx-auto flex h-14 w-full max-w-[1440px] items-center gap-3 px-3 sm:px-4 lg:px-6">
          <Skeleton className="size-9 shrink-0 rounded-xl" />
          <div className="space-y-1.5">
            <Skeleton className="h-3.5 w-32" />
            <Skeleton className="h-2.5 w-48" />
          </div>
          <Skeleton className="ml-auto h-6 w-20 rounded-full" />
        </div>
      </header>

      <main className="mx-auto grid w-full max-w-[1440px] flex-1 items-start gap-4 px-3 py-4 sm:px-4 lg:grid-cols-[minmax(0,1fr)_380px] lg:px-6 xl:grid-cols-[minmax(0,1fr)_410px]">
        <Skeleton className="h-[72vh] min-h-[520px] rounded-2xl lg:h-[calc(100dvh-8.5rem)] lg:min-h-[560px]" />
        <div className="space-y-4">
          <Skeleton className="h-40 rounded-xl" />
          <Skeleton className="h-[420px] rounded-xl" />
        </div>
      </main>
    </div>
  );
}

export function AssistantApp() {
  const mounted = useMounted();
  const sessionId = useSessionStore((state) => state.sessionId);

  const healthQuery = useHealthQuery(mounted);
  const filesQuery = useFilesQuery(mounted);

  const fileNames = useMemo(
    () =>
      new Map((filesQuery.data ?? []).map((file) => [file.id, file.filename])),
    [filesQuery.data],
  );

  if (!mounted) return <DashboardSkeleton />;

  return (
    <div className="flex flex-1 flex-col">
      <AppHeader healthQuery={healthQuery} />

      <main className="mx-auto w-full max-w-[1440px] flex-1 px-3 py-4 sm:px-4 lg:px-6">
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_380px] xl:grid-cols-[minmax(0,1fr)_410px]">
          <ChatPanel
            sessionId={sessionId}
            fileNames={fileNames}
            hasFiles={(filesQuery.data?.length ?? 0) > 0}
          />

          <aside className="flex flex-col gap-4">
            <ServiceStatus query={healthQuery} />
            <KnowledgePanel />
          </aside>
        </div>
      </main>

      <footer className="border-t border-border/60 py-3 text-center text-[10px] text-muted-foreground">
        FastAPI · LangGraph · Milvus · Next.js
      </footer>
    </div>
  );
}
