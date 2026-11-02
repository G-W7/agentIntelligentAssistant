import {
  BookOpen,
  ChevronDown,
  ExternalLink,
  FileText,
  Link2,
} from "lucide-react";

import {
  formatScore,
  hostnameOf,
  safeHttpUrl,
  shortId,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import type { SourceItem } from "@/lib/types";

function KnowledgeSource({
  source,
  fileName,
}: {
  source: SourceItem;
  fileName?: string;
}) {
  const label =
    fileName ??
    (source.file_id ? `文档 ${shortId(source.file_id)}` : "知识库片段");
  const location = source.page ? `第 ${source.page} 页` : "页码未知";

  return (
    <li className="rounded-md border border-border/60 bg-background/70 p-2.5">
      <div className="flex items-start gap-2">
        <FileText className="mt-0.5 size-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
        <div className="min-w-0 flex-1">
          <p
            className="truncate text-xs font-medium text-foreground"
            title={source.file_id ? `文件 ID：${source.file_id}` : label}
          >
            {label}
          </p>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            {location} · 相关度 {formatScore(source.score)}
          </p>
          {source.content ? (
            <p
              className="mt-1 line-clamp-2 break-words text-[11px] leading-5 text-muted-foreground"
              title={source.content}
            >
              {source.content}
            </p>
          ) : null}
        </div>
      </div>
    </li>
  );
}

function WebSource({ source }: { source: SourceItem }) {
  const url = safeHttpUrl(source.url);
  const host = hostnameOf(source.url);
  const label = source.title?.trim() || host || "网页来源";

  return (
    <li className="rounded-md border border-border/60 bg-background/70 p-2.5">
      <div className="flex items-start gap-2">
        <Link2 className="mt-0.5 size-3.5 shrink-0 text-sky-600 dark:text-sky-400" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1">
            {typeof source.index === "number" ? (
              <span className="shrink-0 text-[11px] font-medium text-muted-foreground">
                [{source.index}]
              </span>
            ) : null}
            {url ? (
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex min-w-0 items-center gap-1 text-xs font-medium text-foreground underline-offset-3 hover:underline"
                title={url}
              >
                <span className="truncate">{label}</span>
                <ExternalLink className="size-3 shrink-0" />
              </a>
            ) : (
              <span className="truncate text-xs font-medium">{label}</span>
            )}
          </div>
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            {host ? `${host} · ` : ""}相关度 {formatScore(source.score)}
          </p>
          {source.content ? (
            <p
              className="mt-1 line-clamp-2 break-words text-[11px] leading-5 text-muted-foreground"
              title={source.content}
            >
              {source.content}
            </p>
          ) : null}
        </div>
      </div>
    </li>
  );
}

export function SourcesList({
  sources,
  fileNames,
}: {
  sources: SourceItem[];
  fileNames: Map<string, string>;
}) {
  if (sources.length === 0) return null;

  return (
    <details
      className={cn(
        "group mt-3 rounded-lg border border-border/60 bg-muted/25 px-3 py-2",
        "open:bg-muted/35",
      )}
    >
      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground [&::-webkit-details-marker]:hidden">
        <BookOpen className="size-3.5" />
        <span>参考来源</span>
        <span className="rounded-full bg-background px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground ring-1 ring-border/60">
          {sources.length}
        </span>
        <ChevronDown className="ml-auto size-3.5 transition-transform duration-200 group-open:rotate-180" />
      </summary>
      <ol className="mt-2 space-y-1.5">
        {sources.map((source, index) =>
          source.kind === "knowledge" ? (
            <KnowledgeSource
              key={`knowledge-${source.file_id ?? "unknown"}-${source.page ?? "no-page"}-${index}`}
              source={source}
              fileName={
                source.file_id ? fileNames.get(source.file_id) : undefined
              }
            />
          ) : (
            <WebSource
              key={`web-${source.index ?? index}-${source.url ?? "no-url"}`}
              source={source}
            />
          ),
        )}
      </ol>
    </details>
  );
}
