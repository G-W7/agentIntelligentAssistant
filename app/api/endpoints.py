"""RESTful 路由层（设计文档 5）。

涉及阻塞式数据库调用的接口定义为同步函数，由 FastAPI 自动放入线程池执行；
需要 await Agent 图的 /chat 则在内部用 asyncio.to_thread 包装阻塞调用。
"""

import asyncio
import logging
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.db import milvus_client, pg_client
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    DeleteResponse,
    FileItem,
    HealthResponse,
    HistoryItem,
    UploadResponse,
)
from app.services import chat_service, knowledge_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.post("/chat", response_model=ChatResponse, summary="发送消息并获取 Agent 响应")
async def chat(payload: ChatRequest) -> ChatResponse:
    """对话接口：把用户消息交给 Agent 图处理。

    依赖服务不可用返回 503；Agent 执行异常返回 502。
    """
    try:
        result = await chat_service.chat(payload.session_id, payload.message)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"依赖服务不可用：{exc}") from exc
    except Exception as exc:
        logger.exception("Agent 执行失败")
        raise HTTPException(status_code=502, detail=f"Agent 执行失败：{exc}") from exc
    return ChatResponse(**result)


@router.post("/upload", response_model=UploadResponse, summary="上传知识库文件")
async def upload(file: UploadFile = File(...)) -> UploadResponse:
    """上传接口：读入文件字节后，在线程池中执行"落盘 + 切片向量化"。

    文件不合规返回 400；依赖服务不可用返回 503；向量化失败返回 502。
    """
    raw = await file.read()
    try:
        result = await asyncio.to_thread(
            knowledge_service.upload_and_ingest, file.filename or "", raw
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"依赖服务不可用：{exc}") from exc
    except Exception as exc:
        logger.exception("文件向量化失败")
        raise HTTPException(
            status_code=502, detail=f"向量化失败，文件状态已置为 error：{exc}"
        ) from exc
    return UploadResponse(**result)


@router.get("/history", response_model=list[HistoryItem], summary="获取历史对话")
def get_history(
    session_id: str = Query("default", max_length=100),
    limit: int = Query(50, ge=1, le=200),
) -> list[HistoryItem]:
    """历史接口：查询指定会话最近 limit 条消息（同步函数，FastAPI 自动放线程池）。"""
    rows = chat_service.history(session_id, limit)
    return [HistoryItem(**row) for row in rows]


@router.get("/files", response_model=list[FileItem], summary="获取已上传文件列表")
def list_files() -> list[FileItem]:
    """文件列表接口：返回知识库全部已上传文件及其处理状态。"""
    return [FileItem(**row) for row in knowledge_service.list_files()]


@router.delete("/files/{file_id}", response_model=DeleteResponse, summary="删除指定文件及向量")
def delete_file(file_id: UUID) -> DeleteResponse:
    """删除接口：级联删除文件的向量、元数据与磁盘文件。

    文件不存在返回 404；依赖服务不可用返回 503。
    """
    try:
        return DeleteResponse(**knowledge_service.delete_file(str(file_id)))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"依赖服务不可用：{exc}") from exc


@router.get("/health", response_model=HealthResponse, summary="依赖服务健康状态")
def health() -> HealthResponse:
    """健康检查接口：分别探测 PostgreSQL 与 Milvus 可用性。

    两者均正常返回 ok，任一异常返回 degraded，并附带向量数与文件数统计。
    """
    postgres_ok = False
    file_count = 0
    try:
        file_count = len(pg_client.list_files())
        postgres_ok = True
    except Exception:
        logger.warning("健康检查：PostgreSQL 不可用", exc_info=True)

    milvus_ok = False
    vector_count = 0
    try:
        stats = milvus_client.collection_stats()
        milvus_ok = stats["exists"]
        vector_count = stats["row_count"]
    except Exception:
        logger.warning("健康检查：Milvus 不可用", exc_info=True)

    return HealthResponse(
        status="ok" if postgres_ok and milvus_ok else "degraded",
        postgres=postgres_ok,
        milvus=milvus_ok,
        milvus_vectors=vector_count,
        knowledge_files=file_count,
    )
