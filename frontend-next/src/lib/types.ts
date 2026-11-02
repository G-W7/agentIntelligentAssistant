/** 与后端 app/models/schemas.py 保持一致的类型契约。 */

export type Route = "rag" | "chat" | "search";

export type ChatRole = "user" | "assistant";

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
}
