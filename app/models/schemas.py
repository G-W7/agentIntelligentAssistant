"""API 层的 Pydantic 模型（请求 / 响应契约）。"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# 路由目标与消息角色的字面量类型别名
Route = Literal["rag", "chat", "search"]
Role = Literal["user", "assistant"]


class ChatRequest(BaseModel):
    """/api/chat 请求体：用户消息与会话标识。"""

    message: str = Field(min_length=1, max_length=8000, description="用户消息")
    session_id: str = Field(default="default", max_length=100, description="会话标识")


class SourceItem(BaseModel):
    """回答的引用来源，knowledge 为知识库片段，web 为联网搜索结果。"""

    kind: Literal["knowledge", "web"]
    title: str | None = None
    url: str | None = None
    file_id: str | None = None
    page: int | None = None
    index: int | None = None
    score: float = 0.0
    content: str = ""


class ChatResponse(BaseModel):
    """/api/chat 响应体：会话 ID、路由结果及理由、最终回答与引用来源列表。"""

    session_id: str
    route: Route
    route_reason: str = ""
    answer: str
    sources: list[SourceItem] = Field(default_factory=list)


class HistoryItem(BaseModel):
    """单条历史消息：id、角色、内容、元数据（路由 / 来源）与创建时间。"""

    id: int
    role: Role
    content: str
    metadata: dict[str, Any] | None = None
    created_at: datetime


class FileItem(BaseModel):
    """知识库文件条目：id、文件名、类型、大小、上传时间与处理状态。"""

    id: str
    filename: str
    file_type: str | None = None
    file_size: int | None = None
    upload_time: datetime | None = None
    status: str = "processing"


class UploadResponse(BaseModel):
    """/api/upload 响应体：入库后的文件记录与切片数量。"""

    file: FileItem
    chunk_count: int


class DeleteResponse(BaseModel):
    """DELETE /api/files/{id} 响应体：被删文件 ID 与删除的向量条数。"""

    file_id: str
    deleted_vectors: int


class HealthResponse(BaseModel):
    """/api/health 响应体：整体状态与各依赖服务的可用性统计。"""

    status: Literal["ok", "degraded"]
    postgres: bool
    milvus: bool
    milvus_vectors: int = 0
    knowledge_files: int = 0
