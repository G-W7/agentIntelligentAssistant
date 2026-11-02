"""对话业务逻辑：装载会话状态 → 调用 Agent 图 → 持久化。

对应设计文档 8「状态管理」：LangGraph Checkpointer 负责进程内的
多轮上下文，PostgreSQL chat_history 负责跨重启的持久化与前端展示。
"""

import asyncio
import logging
from typing import Any, AsyncIterator

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
)

from app.config import get_settings
from app.core.agent_graph import WORKER_NODES, get_graph
from app.core.observability import build_callbacks
from app.db import pg_client

logger = logging.getLogger(__name__)

# 角色名 → LangChain 消息类的映射，用于从数据库行还原消息对象
_ROLE_CLASSES = {"user": HumanMessage, "assistant": AIMessage}

# 与 MemorySaver 的生命周期一致（都是进程级），用于判断某个会话是否
# 已经在本进程内预热过图状态，避免每轮都重复从 PostgreSQL 灌历史。
# 键为 (user_id, session_id)，防止不同用户的同名会话相互干扰。
_warmed_sessions: set[tuple[str, str]] = set()

# 允许向前端推送 token 的节点集合（router 使用结构化输出，其 token 是
# JSON 片段，不应作为回答内容展示）。
_STREAMABLE_NODES: frozenset[str] = frozenset(WORKER_NODES.values())


def _text_of(message: BaseMessage) -> str:
    """兼容 content 为字符串或多模态分块列表两种形态。"""
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(
        part.get("text", "") for part in content if isinstance(part, dict)
    )


def _load_history(session_id: str, user_id: str) -> list[BaseMessage]:
    """从 PostgreSQL 读取指定用户某会话最近 history_window 条历史，按角色还原为消息对象列表。"""
    rows = pg_client.list_messages(
        session_id, user_id, limit=get_settings().history_window
    )
    messages: list[BaseMessage] = []
    for row in rows:
        message_class = _ROLE_CLASSES.get(row["role"])
        if message_class is not None:
            messages.append(message_class(content=row["content"]))
    return messages


def _build_graph_config(session_id: str, user_id: str) -> dict[str, Any]:
    """统一构造 LangGraph 调用配置（thread_id / Langfuse 回调与 metadata）。

    thread_id 拼接 user_id，保证不同用户即使用相同 session_id（如 default）
    也不会共享 MemorySaver 里的图状态，避免跨用户上下文泄露。
    """
    return {
        "configurable": {"thread_id": f"{user_id}:{session_id}"},
        # Langfuse 未启用时 build_callbacks() 返回 []，不影响正常执行
        "callbacks": build_callbacks(),
        "metadata": {
            # 以下三个 key 是 Langfuse v3 约定的字段名，会被自动识别为 trace 属性
            "langfuse_session_id": session_id,
            "langfuse_tags": ["agent-assistant"],
        },
    }


async def _prepare_session(session_id: str, user_id: str, message: str) -> list[BaseMessage]:
    """首次访问会话时灌入历史 seed，并把本轮用户消息落库。"""
    warm_key = (user_id, session_id)
    if warm_key in _warmed_sessions:
        seed: list[BaseMessage] = []
    else:
        seed = await asyncio.to_thread(_load_history, session_id, user_id)
        _warmed_sessions.add(warm_key)

    # 必须在写入本轮用户消息之前取历史，否则 seed 会与 messages 末尾重复
    await asyncio.to_thread(
        pg_client.save_message, session_id, "user", message, user_id
    )
    return seed


async def chat(session_id: str, user_id: str, message: str) -> dict[str, Any]:
    """对话主流程：装载历史 → 调用 Agent 图 → 持久化本轮消息。

    步骤：
    1. 会话首次出现时从 PG 灌入历史作为 seed（_warmed_sessions 防重复加载）；
    2. 先把本轮用户消息落库（必须在取 seed 之后，避免与 messages 末尾重复）；
    3. 以 thread_id=session_id 调用 Agent 图，进程内多轮上下文由 MemorySaver 维持；
    4. 提取回答文本，把 assistant 消息（含路由与来源元数据）落库；
    5. 返回结构化结果供路由层组装 ChatResponse。
    """
    graph = get_graph()
    config = _build_graph_config(session_id, user_id)
    seed = await _prepare_session(session_id, user_id, message)

    result = await graph.ainvoke(
        {
            "messages": [*seed, HumanMessage(content=message)],
            "session_id": session_id,
            "user_id": user_id,
            "sources": [],
        },
        config=config,
    )

    answer = _text_of(result["messages"][-1])
    route = result.get("route", "chat")
    route_reason = result.get("route_reason", "")
    sources = result.get("sources", [])

    await asyncio.to_thread(
        pg_client.save_message,
        session_id,
        "assistant",
        answer,
        user_id,
        {"route": route, "route_reason": route_reason, "sources": sources},
    )

    return {
        "session_id": session_id,
        "route": route,
        "route_reason": route_reason,
        "answer": answer,
        "sources": sources,
    }


async def chat_stream(session_id: str, user_id: str, message: str) -> AsyncIterator[dict[str, Any]]:
    """流式对话主流程：以 SSE 事件字典的形式逐步产出。

    事件类型（前端按 type 分派）：
    - start：会话已就绪，可开始接收增量；携带 session_id。
    - route：router 节点完成后产出，携带 route / route_reason。
    - delta：worker 节点 LLM token 增量，携带 content。
    - sources：worker 节点完成后产出，携带 sources 列表。
    - done：全部结束，携带最终 answer 与元数据；此时助手消息已落库。
    """
    graph = get_graph()
    config = _build_graph_config(session_id, user_id)
    seed = await _prepare_session(session_id, user_id, message)

    yield {"type": "start", "session_id": session_id}

    route: str = "chat"
    route_reason: str = ""
    sources: list[dict[str, Any]] = []
    answer_parts: list[str] = []
    route_emitted = False
    sources_emitted = False

    async for mode, chunk in graph.astream(
        {
            "messages": [*seed, HumanMessage(content=message)],
            "session_id": session_id,
            "user_id": user_id,
            "sources": [],
        },
        config=config,
        stream_mode=["messages", "updates"],
    ):
        if mode == "messages":
            # chunk = (message_chunk, metadata)
            message_chunk, metadata = chunk
            node = metadata.get("langgraph_node") if isinstance(metadata, dict) else None
            if node not in _STREAMABLE_NODES:
                continue
            if not isinstance(message_chunk, AIMessageChunk):
                continue
            text = _text_of(message_chunk)
            if text:
                answer_parts.append(text)
                yield {"type": "delta", "content": text}
            continue

        if mode == "updates":
            # chunk = {node_name: state_delta}
            if not isinstance(chunk, dict):
                continue
            for node_name, delta in chunk.items():
                if not isinstance(delta, dict):
                    continue
                if node_name == "router" and not route_emitted:
                    route = delta.get("route", route) or route
                    route_reason = delta.get("route_reason", "") or ""
                    route_emitted = True
                    yield {
                        "type": "route",
                        "route": route,
                        "route_reason": route_reason,
                    }
                elif node_name in _STREAMABLE_NODES:
                    node_sources = delta.get("sources") or []
                    if node_sources and not sources_emitted:
                        sources = list(node_sources)
                        sources_emitted = True
                        yield {"type": "sources", "sources": sources}
                    # 兜底：worker 走了非 LLM 分支（如"知识库未检索到"/搜索异常），
                    # 此时 messages 模式没有 token，需要把最终 AIMessage 一次性推给前端。
                    node_messages = delta.get("messages") or []
                    if node_messages and not answer_parts:
                        final_text = _text_of(node_messages[-1])
                        if final_text:
                            answer_parts.append(final_text)
                            yield {"type": "delta", "content": final_text}

    answer = "".join(answer_parts)
    await asyncio.to_thread(
        pg_client.save_message,
        session_id,
        "assistant",
        answer,
        user_id,
        {"route": route, "route_reason": route_reason, "sources": sources},
    )

    yield {
        "type": "done",
        "session_id": session_id,
        "answer": answer,
        "route": route,
        "route_reason": route_reason,
        "sources": sources,
    }


def history(session_id: str, user_id: str, limit: int) -> list[dict[str, Any]]:
    """查询指定用户某会话的历史消息（时间正序），供 /api/history 使用。"""
    return pg_client.list_messages(session_id, user_id, limit=limit)


def delete_session(session_id: str, user_id: str) -> dict[str, Any]:
    """删除指定用户某会话的全部聊天记录，供 DELETE /api/sessions/{session_id} 使用。"""
    deleted = pg_client.delete_session(session_id, user_id)
    return {"session_id": session_id, "deleted_messages": deleted}


def list_sessions(user_id: str, limit: int) -> list[dict[str, Any]]:
    """查询指定用户的会话列表（最近活跃在前），供 /api/sessions 使用。"""
    return pg_client.list_sessions(user_id, limit=limit)
