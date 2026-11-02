"use client";

import { useRef, useState, type DragEvent, type KeyboardEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  CloudUpload,
  FileText,
  Loader2,
  X,
  XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { queryKeys } from "@/hooks/queries";
import { api, getErrorMessage } from "@/lib/api";
import {
  ACCEPTED_FILE_EXTENSIONS,
  ACCEPT_ATTRIBUTE,
  MAX_UPLOAD_MB,
} from "@/lib/constants";
import { humanSize } from "@/lib/format";
import { cn } from "@/lib/utils";

interface UploadResult {
  key: string;
  name: string;
  ok: boolean;
  message: string;
}

function fileKey(file: File): string {
  return `${file.name}::${file.size}::${file.lastModified}`;
}

function validateFile(file: File): string | null {
  const lowerName = file.name.toLowerCase();
  if (!ACCEPTED_FILE_EXTENSIONS.some((extension) => lowerName.endsWith(extension))) {
    return "不支持的文件类型";
  }
  if (file.size === 0) return "文件内容为空";
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return `文件超过 ${MAX_UPLOAD_MB} MB 上限`;
  }
  return null;
}

export function FileUploader() {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [selected, setSelected] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState<{
    current: number;
    total: number;
  } | null>(null);
  const [results, setResults] = useState<UploadResult[]>([]);

  function addFiles(files: FileList | File[]) {
    const incoming = Array.from(files);
    if (incoming.length === 0) return;

    setSelected((current) => {
      const keys = new Set(current.map(fileKey));
      const next = [...current];
      for (const file of incoming) {
        const key = fileKey(file);
        if (!keys.has(key)) {
          keys.add(key);
          next.push(file);
        }
      }
      return next;
    });
    setResults([]);
  }

  function removeFile(key: string) {
    if (uploading) return;
    setSelected((current) => current.filter((file) => fileKey(file) !== key));
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    addFiles(event.dataTransfer.files);
  }

  function handleDropZoneKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      inputRef.current?.click();
    }
  }

  async function handleUpload() {
    if (selected.length === 0 || uploading) return;

    setUploading(true);
    setResults([]);

    const collected: UploadResult[] = [];
    const succeeded = new Set<string>();
    const total = selected.length;

    for (let index = 0; index < selected.length; index += 1) {
      const file = selected[index];
      const key = fileKey(file);
      setProgress({ current: index + 1, total });

      const validationError = validateFile(file);
      if (validationError) {
        collected.push({ key, name: file.name, ok: false, message: validationError });
        setResults([...collected]);
        continue;
      }

      try {
        const response = await api.upload(file);
        if (response.file.status === "ready") {
          succeeded.add(key);
          collected.push({
            key,
            name: file.name,
            ok: true,
            message: `已入库，生成 ${response.chunk_count} 个切片`,
          });
        } else {
          collected.push({
            key,
            name: file.name,
            ok: false,
            message: `文件状态为 ${response.file.status}，未生成有效切片`,
          });
        }
      } catch (error) {
        collected.push({
          key,
          name: file.name,
          ok: false,
          message: getErrorMessage(error),
        });
      }
      setResults([...collected]);
    }

    setUploading(false);
    setProgress(null);
    setSelected((current) =>
      current.filter((file) => !succeeded.has(fileKey(file))),
    );

    if (succeeded.size > 0) {
      void queryClient.invalidateQueries({ queryKey: queryKeys.files });
      void queryClient.invalidateQueries({ queryKey: queryKeys.health });
    }
  }

  return (
    <div className="space-y-3">
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPT_ATTRIBUTE}
        className="sr-only"
        onChange={(event) => {
          if (event.target.files) addFiles(event.target.files);
          event.target.value = "";
        }}
      />

      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={handleDropZoneKeyDown}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={(event) => {
          if (
            !event.currentTarget.contains(event.relatedTarget as Node | null)
          ) {
            setDragging(false);
          }
        }}
        onDrop={handleDrop}
        className={cn(
          "cursor-pointer rounded-xl border border-dashed px-3 py-4 text-center transition-colors outline-none",
          "focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
          dragging
            ? "border-indigo-500 bg-indigo-500/5"
            : "border-border bg-muted/20 hover:border-border/80 hover:bg-muted/40",
        )}
      >
        <CloudUpload className="mx-auto size-6 text-muted-foreground" />
        <p className="mt-2 text-xs font-medium">
          拖拽文件到这里，或{" "}
          <span className="text-indigo-600 underline underline-offset-2 dark:text-indigo-400">
            选择文件
          </span>
        </p>
        <p className="mt-1 text-[10px] leading-4 text-muted-foreground">
          PDF / Markdown / TXT / Word / PPT / Excel / 图片
          <br />
          单个文件不超过 {MAX_UPLOAD_MB} MB
        </p>
      </div>

      {selected.length > 0 ? (
        <ul className="space-y-1.5">
          {selected.map((file) => (
            <li
              key={fileKey(file)}
              className="flex items-center gap-2 rounded-lg border border-border/60 bg-background/60 px-2.5 py-1.5"
            >
              <FileText className="size-3.5 shrink-0 text-muted-foreground" />
              <span
                className="min-w-0 flex-1 truncate text-xs"
                title={file.name}
              >
                {file.name}
              </span>
              <span className="shrink-0 text-[10px] text-muted-foreground">
                {humanSize(file.size)}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="icon-xs"
                onClick={() => removeFile(fileKey(file))}
                disabled={uploading}
                aria-label={`移除 ${file.name}`}
                title="移除"
              >
                <X className="size-3" />
              </Button>
            </li>
          ))}
        </ul>
      ) : null}

      <Button
        type="button"
        onClick={() => {
          void handleUpload();
        }}
        disabled={selected.length === 0 || uploading}
        className="w-full"
      >
        {uploading ? (
          <>
            <Loader2 className="size-4 animate-spin" />
            正在处理 {progress?.current ?? 0}/{progress?.total ?? selected.length}…
          </>
        ) : (
          <>
            <CloudUpload className="size-4" />
            上传并向量化
          </>
        )}
      </Button>

      {results.length > 0 ? (
        <ul className="space-y-1">
          {results.map((result) => (
            <li
              key={result.key}
              className={cn(
                "flex items-start gap-1.5 rounded-md px-2 py-1 text-[11px] leading-5",
                result.ok
                  ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                  : "bg-destructive/10 text-destructive",
              )}
            >
              {result.ok ? (
                <CheckCircle2 className="mt-0.5 size-3.5 shrink-0" />
              ) : (
                <XCircle className="mt-0.5 size-3.5 shrink-0" />
              )}
              <span className="min-w-0 flex-1 break-words">
                <span className="font-medium">{result.name}</span>：{result.message}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
