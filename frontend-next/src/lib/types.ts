/** 与后端 app/models/schemas.py 保持一致的类型契约。 */

export type Route = "rag" | "chat" | "search";

export type ChatRole = "user" | "assistant";

export interface User {
  id: string;
  username: string;
  created_at: string | null;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface AuthPayload {
  username: string;
  password: string;
}

export interface SourceItem {
  kind: "knowledge" | "web";
  title?: string | null;
  url?: string | null;
  file_id?: string | null;
  page?: number | null;
  index?: number | null;
  score: number;
  content?: string;
}

export interface MessageMetadata {
  route?: Route;
  route_reason?: string;
  sources?: SourceItem[];
}

export interface ChatResponse {
  session_id: string;
  route: Route;
  route_reason: string;
  answer: string;
  sources: SourceItem[];
}

export interface HistoryItem {
  id: number;
  role: ChatRole;
  content: string;
  metadata: MessageMetadata | null;
  created_at: string;
}

export interface SessionItem {
  session_id: string;
  last_message_at: string;
  message_count: number;
  preview: string;
}

export interface DeleteSessionResponse {
  session_id: string;
  deleted_messages: number;
}

export interface FileItem {
  id: string;
  filename: string;
  file_type: string | null;
  file_size: number | null;
  upload_time: string | null;
  status: string;
}

export interface UploadResponse {
  file: FileItem;
  chunk_count: number;
}

export interface DeleteResponse {
  file_id: string;
  deleted_vectors: number;
}

export type HealthStatus = "ok" | "degraded";

export interface HealthResponse {
  status: HealthStatus;
  postgres: boolean;
  milvus: boolean;
  milvus_vectors: number;
  knowledge_files: number;
}

/** 前端统一使用的消息模型：历史消息与本次新消息共用。 */
export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  metadata: MessageMetadata | null;
  createdAt: string | null;
  /** 仅本地使用：助手消息是否正在流式接收中。 */
  streaming?: boolean;
}

/** 与后端 /api/chat/stream 的 SSE 事件契约保持一致。 */
export type ChatStreamEvent =
  | { type: "start"; session_id: string }
  | { type: "route"; route: Route; route_reason: string }
  | { type: "delta"; content: string }
  | { type: "sources"; sources: SourceItem[] }
  | {
      type: "done";
      session_id: string;
      answer: string;
      route: Route;
      route_reason: string;
      sources: SourceItem[];
    }
  | { type: "error"; message: string };
