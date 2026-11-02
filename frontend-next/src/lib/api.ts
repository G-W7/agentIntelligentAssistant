/**
 * FastAPI 访问层。
 *
 * 默认走同源的 `/backend/*`，由 next.config.ts 的 rewrites 代理到
 * BACKEND_BASE_URL/api/*，浏览器无需处理 CORS。
 * 如需浏览器直连后端，可设置 NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000。
 */

import type {
  ChatResponse,
  DeleteResponse,
  FileItem,
  HealthResponse,
  HistoryItem,
  UploadResponse,
} from "@/lib/types";

const configuredBase = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();

export const API_BASE = configuredBase
  ? configuredBase.replace(/\/+$/, "")
  : "/backend";

export class ApiError extends Error {
  readonly status: number | null;

  constructor(message: string, status: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function detailToMessage(body: unknown, fallback: string): string {
  if (typeof body === "string" && body.trim()) return body;
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) => {
          if (item && typeof item === "object" && "msg" in item) {
            return String((item as { msg: unknown }).msg);
          }
          return JSON.stringify(item);
        })
        .filter(Boolean);
      if (messages.length > 0) return messages.join("；");
    }
  }
  return fallback;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs?: number,
): Promise<T> {
  const headers = new Headers(init.headers);
  if (
    init.body &&
    !(init.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set("Content-Type", "application/json");
  }

  const timeoutSignal = timeoutMs ? AbortSignal.timeout(timeoutMs) : null;
  const signal =
    init.signal && timeoutSignal
      ? AbortSignal.any([init.signal, timeoutSignal])
      : (init.signal ?? timeoutSignal ?? undefined);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      signal,
      cache: "no-store",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new ApiError(
        `请求超时（${Math.round((timeoutMs ?? 0) / 1000)} 秒），请稍后重试`,
      );
    }
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new ApiError(
      `无法连接后端服务：${error instanceof Error ? error.message : String(error)}`,
    );
  }

  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      try {
        body = await response.text();
      } catch {
        body = null;
      }
    }
    throw new ApiError(
      detailToMessage(body, `请求失败（HTTP ${response.status}）`),
      response.status,
    );
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  return JSON.stringify(error);
}

export const api = {
  health(signal?: AbortSignal): Promise<HealthResponse> {
    return request<HealthResponse>("/health", { signal }, 15_000);
  },

  files(signal?: AbortSignal): Promise<FileItem[]> {
    return request<FileItem[]>("/files", { signal }, 30_000);
  },

  history(
    sessionId: string,
    limit = 200,
    signal?: AbortSignal,
  ): Promise<HistoryItem[]> {
    const params = new URLSearchParams({
      session_id: sessionId,
      limit: String(limit),
    });
    return request<HistoryItem[]>(`/history?${params}`, { signal }, 30_000);
  },

  chat(payload: {
    message: string;
    session_id: string;
  }): Promise<ChatResponse> {
    return request<ChatResponse>(
      "/chat",
      {
        method: "POST",
        body: JSON.stringify(payload),
      },
      300_000,
    );
  },

  upload(file: File): Promise<UploadResponse> {
    const form = new FormData();
    form.append("file", file, file.name);
    return request<UploadResponse>(
      "/upload",
      { method: "POST", body: form },
      600_000,
    );
  },

  deleteFile(fileId: string): Promise<DeleteResponse> {
    return request<DeleteResponse>(
      `/files/${encodeURIComponent(fileId)}`,
      { method: "DELETE" },
      120_000,
    );
  },
};
