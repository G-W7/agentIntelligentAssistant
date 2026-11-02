"use client";

import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Copy,
  FileText,
  Loader2,
  RefreshCw,
  Trash2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { queryKeys } from "@/hooks/queries";
import { api, getErrorMessage } from "@/lib/api";
import { FILE_TYPE_LABELS } from "@/lib/constants";
import {
  formatDateTime,
  humanSize,
  shortId,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import type { FileItem } from "@/lib/types";

const STATUS_META: Record<string, { label: string; className: string }> = {
  ready: {
    label: "已就绪",
    className:
      "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  },
  processing: {
    label: "处理中",
    className:
      "border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  },
  error: {
    label: "失败",
    className: "border-destructive/20 bg-destructive/10 text-destructive",
  },
};

function typeLabel(fileType: string | null): string {
  if (!fileType) return "—";
  return FILE_TYPE_LABELS[fileType.toLowerCase()] ?? fileType.toUpperCase();
}

function FileStatusBadge({ status }: { status: string }) {
  const meta = STATUS_META[status] ?? {
    label: status,
    className: "border-border text-muted-foreground",
  };

  return (
    <Badge
      variant="outline"
      className={cn("h-4 px-1.5 text-[10px]", meta.className)}
    >
      {meta.label}
    </Badge>
  );
}

export function FileList({
  files,
  isLoading,
  isFetching,
  error,
  onRetry,
}: {
  files: FileItem[];
  isLoading: boolean;
  isFetching: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  const queryClient = useQueryClient();
  const [target, setTarget] = useState<FileItem | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 6000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const deleteMutation = useMutation({
    mutationFn: (fileId: string) => api.deleteFile(fileId),
    onSuccess: (data) => {
      setNotice(
        `已删除 ${shortId(data.file_id)}，清理 ${data.deleted_vectors} 条向量`,
      );
      setTarget(null);
      setDeleteError(null);
      void queryClient.invalidateQueries({ queryKey: queryKeys.files });
      void queryClient.invalidateQueries({ queryKey: queryKeys.health });
    },
    onError: (mutationError) => {
      setDeleteError(getErrorMessage(mutationError));
    },
  });

  async function copyId(fileId: string) {
    if (!navigator.clipboard) return;
    try {
      await navigator.clipboard.writeText(fileId);
      setCopiedId(fileId);
      window.setTimeout(() => {
        setCopiedId((current) => (current === fileId ? null : current));
      }, 1500);
    } catch {
      // 剪贴板权限被拒绝时静默失败，用户仍可通过 title 查看完整 ID。
    }
  }

  function closeDialog() {
    if (deleteMutation.isPending) return;
    setTarget(null);
    setDeleteError(null);
  }

  return (
    <div className="space-y-2">
      {notice ? (
        <p className="flex items-center gap-1.5 rounded-md bg-emerald-500/10 px-2.5 py-1.5 text-[11px] text-emerald-700 dark:text-emerald-300">
          <CheckCircle2 className="size-3.5 shrink-0" />
          <span className="min-w-0 flex-1 break-words">{notice}</span>
        </p>
      ) : null}

      {error ? (
        <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-center">
          <AlertTriangle className="mx-auto size-5 text-destructive" />
          <p className="mt-1.5 text-xs font-medium text-destructive">
            获取文件列表失败
          </p>
          <p className="mt-1 break-words text-[10px] leading-4 text-muted-foreground">
            {error}
          </p>
          <Button
            variant="outline"
            size="xs"
            onClick={onRetry}
            disabled={isFetching}
            className="mt-2"
          >
            <RefreshCw className={cn("size-3", isFetching && "animate-spin")} />
            重试
          </Button>
        </div>
      ) : isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-16 w-full rounded-lg" />
          <Skeleton className="h-16 w-full rounded-lg" />
          <Skeleton className="h-16 w-full rounded-lg" />
        </div>
      ) : files.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border/70 px-3 py-5 text-center text-[11px] leading-5 text-muted-foreground">
          知识库暂无文件。
          <br />
          上传文档后即可在对话中检索引用。
        </p>
      ) : (
        <ul className="scrollbar-thin max-h-[360px] divide-y divide-border/60 overflow-y-auto rounded-lg border border-border/60">
          {files.map((file) => (
            <li key={file.id} className="flex items-start gap-2.5 p-2.5">
              <div className="grid size-8 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground">
                <FileText className="size-4" />
              </div>

              <div className="min-w-0 flex-1">
                <p
                  className="truncate text-xs font-medium"
                  title={file.filename}
                >
                  {file.filename}
                </p>
                <p className="mt-0.5 truncate text-[10px] text-muted-foreground">
                  {typeLabel(file.file_type)} · {humanSize(file.file_size)} ·{" "}
                  {formatDateTime(file.upload_time)}
                </p>
                <div className="mt-1 flex items-center gap-1.5">
                  <FileStatusBadge status={file.status} />
                  <button
                    type="button"
                    onClick={() => {
                      void copyId(file.id);
                    }}
                    className="inline-flex items-center gap-0.5 rounded px-1 py-0.5 font-mono text-[10px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                    title={`复制文件 ID：${file.id}`}
                  >
                    {copiedId === file.id ? (
                      <Check className="size-2.5" />
                    ) : (
                      <Copy className="size-2.5" />
                    )}
                    {shortId(file.id)}
                  </button>
                </div>
              </div>

              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                onClick={() => {
                  setTarget(file);
                  setDeleteError(null);
                }}
                disabled={deleteMutation.isPending}
                aria-label={`删除 ${file.filename}`}
                title="删除文件及向量"
                className="text-muted-foreground hover:text-destructive"
              >
                <Trash2 className="size-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      )}

      <Dialog
        open={target !== null}
        onOpenChange={(open) => {
          if (!open) closeDialog();
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除文件</DialogTitle>
            <DialogDescription>
              将同时删除{" "}
              <span className="font-medium text-foreground">
                {target?.filename}
              </span>{" "}
              的向量索引和磁盘文件，此操作不可撤销。
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
                if (target) deleteMutation.mutate(target.id);
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
    </div>
  );
}
