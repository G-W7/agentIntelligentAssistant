"""RESTful 路由层（设计文档 5）。

涉及阻塞式数据库调用的接口定义为同步函数，由 FastAPI 自动放入线程池执行；
需要 await Agent 图的 /chat 则在内部用 asyncio.to_thread 包装阻塞调用。
"""

import asyncio
import json
import logging
from typing import Any, AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.db import milvus_client, pg_client
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    DeleteResponse,
    DeleteSessionResponse,
    FileItem,
    HealthResponse,
    HistoryItem,
    SessionItem,
    UploadResponse,
)
from app.services import chat_service, knowledge_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


@router.post("/chat", response_model=ChatResponse, summary="发送消息并获取 Agent 响应")
async def chat(
    payload: ChatRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> ChatResponse:
    """对话接口：把用户消息交给 Agent 图处理。

    依赖服务不可用返回 503；Agent 执行异常返回 502。
    """
    try:
        result = await chat_service.chat(
            payload.session_id, current_user["id"], payload.message
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"依赖服务不可用：{exc}") from exc
    except Exception as exc:
        logger.exception("Agent 执行失败")
        raise HTTPException(status_code=502, detail=f"Agent 执行失败：{exc}") from exc
    return ChatResponse(**result)


def _sse(event_type: str, data: dict) -> str:
    """按 SSE 规范拼装单条事件帧：event 行 + data 行 + 空行结束。"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"


@router.post("/chat/stream", summary="流式发送消息（SSE）")
async def chat_stream(
    payload: ChatRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> StreamingResponse:
    """流式对话接口：以 Server-Sent Events 逐 token 推送 Agent 回答。

    事件类型：start / route / delta / sources / done / error。
    由于响应头一旦发出就无法回退状态码，运行期异常统一以 error 事件下发。
    """
    user_id = current_user["id"]

    async def event_iterator() -> AsyncIterator[str]:
        try:
            async for event in chat_service.chat_stream(
                payload.session_id, user_id, payload.message
            ):
                event_type = event.get("type", "message")
                yield _sse(event_type, event)
        except RuntimeError as exc:
            logger.warning("流式对话依赖服务不可用：%s", exc)
            yield _sse(
                "error",
                {"type": "error", "message": f"依赖服务不可用：{exc}"},
            )
        except asyncio.CancelledError:
            # 客户端断开：向上抛出以便 Starlette 清理任务
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("流式对话执行失败")
            yield _sse(
                "error",
                {"type": "error", "message": f"Agent 执行失败：{exc}"},
            )

    return StreamingResponse(
        event_iterator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # 关闭 Nginx / 反向代理的响应缓冲，保证 token 实时下发
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/upload", response_model=UploadResponse, summary="上传知识库文件")
async def upload(
    file: UploadFile = File(...),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> UploadResponse:
    """上传接口：读入文件字节后，在线程池中执行“落盘 + 切片向量化”。

    文件不合规返回 400；依赖服务不可用返回 503；向量化失败返回 502。
    """
    raw = await file.read()
    try:
        result = await asyncio.to_thread(
            knowledge_service.upload_and_ingest,
            file.filename or "",
            raw,
            current_user["id"],
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
    current_user: dict[str, Any] = Depends(get_current_user),
    session_id: str = Query("default", max_length=100),
    limit: int = Query(50, ge=1, le=200),
) -> list[HistoryItem]:
    """历史接口：查询指定会话最近 limit 条消息（同步函数，FastAPI 自动放线程池）。"""
    rows = chat_service.history(session_id, current_user["id"], limit)
    return [HistoryItem(**row) for row in rows]


@router.get("/sessions", response_model=list[SessionItem], summary="获取会话列表")
def list_sessions(
    current_user: dict[str, Any] = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
) -> list[SessionItem]:
    """会话列表接口：按最近活跃时间倒序返回当前用户的历史会话（同步函数，自动放线程池）。"""
    rows = chat_service.list_sessions(current_user["id"], limit)
    return [SessionItem(**row) for row in rows]


@router.delete("/sessions/{session_id}", response_model=DeleteSessionResponse, summary="删除指定会话")
def delete_session(
    session_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DeleteSessionResponse:
    """删除会话接口：清除该会话全部聊天记录。

    会话不存在（无消息）返回 404。
    """
    result = chat_service.delete_session(session_id, current_user["id"])
    if result["deleted_messages"] == 0:
        raise HTTPException(status_code=404, detail=f"会话 {session_id} 不存在或无消息")
    return DeleteSessionResponse(**result)


@router.get("/files", response_model=list[FileItem], summary="获取已上传文件列表")
def list_files(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[FileItem]:
    """文件列表接口：返回当前用户知识库全部已上传文件及其处理状态。"""
    return [FileItem(**row) for row in knowledge_service.list_files(current_user["id"])]


@router.delete("/files/{file_id}", response_model=DeleteResponse, summary="删除指定文件及向量")
def delete_file(
    file_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DeleteResponse:
    """删除接口：级联删除文件的向量、元数据与磁盘文件。

    文件不存在返回 404；依赖服务不可用返回 503。
    """
    try:
        return DeleteResponse(
            **knowledge_service.delete_file(str(file_id), current_user["id"])
        )
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
        file_count = pg_client.count_files()
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
