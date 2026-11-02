"""API 层的 Pydantic 模型（请求 / 响应契约）。"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# 路由目标与消息角色的字面量类型别名
Route = Literal["rag", "chat", "search"]
Role = Literal["user", "assistant"]


class RegisterRequest(BaseModel):
    """/api/auth/register 请求体：用户名与密码。"""

    # \p{L}/\p{N} 为 Unicode 字母/数字类（Pydantic v2 走 Rust 正则，支持中文），
    # 再放行 . _ @ + - 以兼容邮箱与常见分隔符；空格及其它符号仍被拒绝。
    username: str = Field(min_length=2, max_length=50, pattern=r"^[\p{L}\p{N}._@+-]+$", description="用户名（中英文/数字及 . _ @ + - 符号）")
    password: str = Field(min_length=6, max_length=128, description="密码，至少 6 位")


class LoginRequest(BaseModel):
    """/api/auth/login 请求体。"""

    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    """对外暴露的用户信息（不含密码哈希）。"""

    id: str
    username: str
    created_at: datetime | None = None


class TokenResponse(BaseModel):
    """登录 / 注册成功后的响应体：访问令牌与用户信息。"""

    access_token: str
    token_type: str = "bearer"
    user: UserOut


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


class SessionItem(BaseModel):
    """/api/sessions 单条会话：ID、最后消息时间、消息数与内容预览。"""

    session_id: str
    last_message_at: datetime
    message_count: int
    preview: str = ""


class DeleteSessionResponse(BaseModel):
    """DELETE /api/sessions/{session_id} 响应体。"""

    session_id: str
    deleted_messages: int


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
