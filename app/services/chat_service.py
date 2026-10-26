"""对话业务逻辑：装载会话状态 → 调用 Agent 图 → 持久化。

对应设计文档 8「状态管理」：LangGraph Checkpointer 负责进程内的
多轮上下文，PostgreSQL chat_history 负责跨重启的持久化与前端展示。
"""

import asyncio
import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.config import get_settings
from app.core.agent_graph import get_graph
from app.db import pg_client

logger = logging.getLogger(__name__)

# 角色名 → LangChain 消息类的映射，用于从数据库行还原消息对象
_ROLE_CLASSES = {"user": HumanMessage, "assistant": AIMessage}

# 与 MemorySaver 的生命周期一致（都是进程级），用于判断某个会话是否
# 已经在本进程内预热过图状态，避免每轮都重复从 PostgreSQL 灌历史。
_warmed_sessions: set[str] = set()


def _text_of(message: BaseMessage) -> str:
    """兼容 content 为字符串或多模态分块列表两种形态。"""
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(
        part.get("text", "") for part in content if isinstance(part, dict)
    )


def _load_history(session_id: str) -> list[BaseMessage]:
    """从 PostgreSQL 读取最近 history_window 条历史，按角色还原为消息对象列表。"""
    rows = pg_client.list_messages(session_id, limit=get_settings().history_window)
    messages: list[BaseMessage] = []
    for row in rows:
        message_class = _ROLE_CLASSES.get(row["role"])
        if message_class is not None:
            messages.append(message_class(content=row["content"]))
    return messages


async def chat(session_id: str, message: str) -> dict[str, Any]:
    """对话主流程：装载历史 → 调用 Agent 图 → 持久化本轮消息。

    步骤：
    1. 会话首次出现时从 PG 灌入历史作为 seed（_warmed_sessions 防重复加载）；
    2. 先把本轮用户消息落库（必须在取 seed 之后，避免与 messages 末尾重复）；
    3. 以 thread_id=session_id 调用 Agent 图，进程内多轮上下文由 MemorySaver 维持；
    4. 提取回答文本，把 assistant 消息（含路由与来源元数据）落库；
    5. 返回结构化结果供路由层组装 ChatResponse。
    """
    graph = get_graph()
    config = {"configurable": {"thread_id": session_id}}

    if session_id in _warmed_sessions:
        seed: list[BaseMessage] = []
    else:
        seed = await asyncio.to_thread(_load_history, session_id)
        _warmed_sessions.add(session_id)

    # 必须在写入本轮用户消息之前取历史，否则 seed 会与 messages 末尾重复
    await asyncio.to_thread(pg_client.save_message, session_id, "user", message)

    result = await graph.ainvoke(
        {
            "messages": [*seed, HumanMessage(content=message)],
            "session_id": session_id,
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
        {"route": route, "route_reason": route_reason, "sources": sources},
    )

    return {
        "session_id": session_id,
        "route": route,
        "route_reason": route_reason,
        "answer": answer,
        "sources": sources,
    }


def history(session_id: str, limit: int) -> list[dict[str, Any]]:
    """查询指定会话的历史消息（时间正序），供 /api/history 使用。"""
    return pg_client.list_messages(session_id, limit=limit)
