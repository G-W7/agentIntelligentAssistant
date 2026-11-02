"use client";

import { Database, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { FileList } from "@/components/knowledge/file-list";
import { FileUploader } from "@/components/knowledge/file-uploader";
import { useFilesQuery } from "@/hooks/queries";
import { getErrorMessage } from "@/lib/api";
import { cn } from "@/lib/utils";

export function KnowledgePanel() {
  const filesQuery = useFilesQuery();
  const files = filesQuery.data ?? [];

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="flex flex-row items-center justify-between gap-2 border-b border-border/60 px-4 py-3">
        <CardTitle className="flex items-center gap-2 text-sm">
          <Database className="size-4 text-muted-foreground" />
          知识库
        </CardTitle>
        <div className="flex items-center gap-1.5">
          {filesQuery.data ? (
            <span className="text-[10px] text-muted-foreground">
              {files.length} 个文件
            </span>
          ) : null}
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            onClick={() => {
              void filesQuery.refetch();
            }}
            disabled={filesQuery.isFetching}
            aria-label="刷新文件列表"
            title="刷新文件列表"
          >
            <RefreshCw
              className={cn(
                "size-3.5",
                filesQuery.isFetching && "animate-spin",
              )}
            />
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-4 px-4 py-4">
        <FileUploader />

        <div className="space-y-2">
          <h3 className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
            已上传文件
          </h3>
          <FileList
            files={files}
            isLoading={filesQuery.isLoading}
            isFetching={filesQuery.isFetching}
            error={
              filesQuery.isError ? getErrorMessage(filesQuery.error) : null
            }
            onRetry={() => {
              void filesQuery.refetch();
            }}
          />
        </div>
      </CardContent>
    </Card>
  );
}
