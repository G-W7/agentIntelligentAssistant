/**
 * FastAPI 访问层。
 *
 * 默认走同源的 `/backend/*`，由 next.config.ts 的 rewrites 代理到
 * BACKEND_BASE_URL/api/*，浏览器无需处理 CORS。
 * 如需浏览器直连后端，可设置 NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000。
 */

import type {
  AuthPayload,
  ChatResponse,
  ChatStreamEvent,
  DeleteResponse,
  DeleteSessionResponse,
  FileItem,
  HealthResponse,
  HistoryItem,
  McpStatusResponse,
  SessionItem,
  SkillInfo,
  TokenResponse,
  UploadResponse,
  User,
} from "@/lib/types";

const configuredBase = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();

export const API_BASE = configuredBase
  ? configuredBase.replace(/\/+$/, "")
  : "/backend";

// 访问令牌保存在模块变量中（由 auth-store 写入 / 清除），
// request / chatStream 统一从此处读取并注入 Authorization 头。
let authToken: string | null = null;
let unauthorizedHandler: (() => void) | null = null;

export function setAuthToken(token: string | null): void {
  authToken = token;
}

export function getAuthToken(): string | null {
  return authToken;
}

/** 注册 401 回调：令牌失效时由 auth-store 清除登录态并回到登录页。 */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

function applyAuth(headers: Headers): Headers {
  if (authToken && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${authToken}`);
  }
  return headers;
}

function notifyUnauthorized(status: number): void {
  if (status === 401 && unauthorizedHandler) unauthorizedHandler();
}

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
  applyAuth(headers);

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
    notifyUnauthorized(response.status);
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

/**
 * 解析 SSE 帧：以空行分隔事件，事件内以行首 `data:` 累积负载。
 * 这里忽略 event / id / retry 等字段，因为后端已把事件类型写入 JSON type 字段。
 */
async function* parseSse(
  body: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<ChatStreamEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      if (signal?.aborted) {
        await reader.cancel();
        return;
      }
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // 兼容 \r\n：统一成 \n 后再按空行切帧
      buffer = buffer.replace(/\r\n/g, "\n");

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const rawFrame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf("\n\n");

        const dataLines = rawFrame
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).replace(/^ /, ""));
        if (dataLines.length === 0) continue;

        const dataStr = dataLines.join("\n");
        try {
          yield JSON.parse(dataStr) as ChatStreamEvent;
        } catch {
          // 单帧解析失败不影响后续事件
          console.warn("[SSE] 无法解析事件负载：", dataStr);
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export const api = {
  health(signal?: AbortSignal): Promise<HealthResponse> {
    return request<HealthResponse>("/health", { signal }, 15_000);
  },

  skills(signal?: AbortSignal): Promise<SkillInfo[]> {
    return request<SkillInfo[]>("/skills", { signal }, 15_000);
  },

  mcpStatus(signal?: AbortSignal): Promise<McpStatusResponse> {
    return request<McpStatusResponse>("/mcp/status", { signal }, 30_000);
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

  sessions(limit = 50, signal?: AbortSignal): Promise<SessionItem[]> {
    const params = new URLSearchParams({ limit: String(limit) });
    return request<SessionItem[]>(`/sessions?${params}`, { signal }, 30_000);
  },

  deleteSession(sessionId: string): Promise<DeleteSessionResponse> {
    return request<DeleteSessionResponse>(
      `/sessions/${encodeURIComponent(sessionId)}`,
      { method: "DELETE" },
      30_000,
    );
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

  /**
   * 流式对话：POST /api/chat/stream，返回 SSE 事件的异步迭代器。
   * 传入 AbortSignal 可中途取消（例如组件卸载）。
   */
  async *chatStream(
    payload: { message: string; session_id: string },
    signal?: AbortSignal,
  ): AsyncGenerator<ChatStreamEvent> {
    let response: Response;
    try {
      response = await fetch(`${API_BASE}/chat/stream`, {
        method: "POST",
        headers: applyAuth(
          new Headers({
            "Content-Type": "application/json",
            Accept: "text/event-stream",
          }),
        ),
        body: JSON.stringify(payload),
        signal,
        cache: "no-store",
      });
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        throw error;
      }
      throw new ApiError(
        `无法连接后端服务：${error instanceof Error ? error.message : String(error)}`,
      );
    }

    if (!response.ok || !response.body) {
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
      notifyUnauthorized(response.status);
      throw new ApiError(
        detailToMessage(body, `请求失败（HTTP ${response.status}）`),
        response.status,
      );
    }

    yield* parseSse(response.body, signal);
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

  register(payload: AuthPayload): Promise<TokenResponse> {
    return request<TokenResponse>(
      "/auth/register",
      { method: "POST", body: JSON.stringify(payload) },
      30_000,
    );
  },

  login(payload: AuthPayload): Promise<TokenResponse> {
    return request<TokenResponse>(
      "/auth/login",
      { method: "POST", body: JSON.stringify(payload) },
      30_000,
    );
  },

  me(signal?: AbortSignal): Promise<User> {
    return request<User>("/auth/me", { signal }, 15_000);
  },
};
