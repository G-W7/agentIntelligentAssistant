"""LangGraph 编排：主管-工作者拓扑（设计文档 4.1、8）。"""

import logging
from functools import lru_cache
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.core.agents import (
    AgentState,
    Destination,
    chat_worker,
    rag_worker,
    router_node,
    search_worker,
)

logger = logging.getLogger(__name__)

# 路由目标 → 工作者节点名的映射，同时作为条件边的分支表
WORKER_NODES: dict[Destination, str] = {
    "rag": "rag",
    "search": "search",
    "chat": "chat",
}


def route_decision(state: AgentState) -> str:
    """条件边：把主管给出的 destination 映射到工作者节点名。"""
    return WORKER_NODES.get(state.get("route", "chat"), "chat")


@lru_cache
def get_graph() -> Any:
    """构建并缓存 LangGraph 图（进程内只编译一次）。

    拓扑：START → router →(条件分发 route_decision)→ rag / search / chat → END。
    """
    builder = StateGraph(AgentState)

    builder.add_node("router", router_node)
    builder.add_node("rag", rag_worker)
    builder.add_node("search", search_worker)
    builder.add_node("chat", chat_worker)

    builder.add_edge(START, "router")
    builder.add_conditional_edges("router", route_decision, WORKER_NODES)
    for node in WORKER_NODES.values():
        builder.add_edge(node, END)

    # MemorySaver 只在进程存活期间保留状态，跨重启的多轮记忆由
    # PostgreSQL chat_history 兜底（见 chat_service）。需要真正的断点续传时，
    # 换成 langgraph-checkpoint-postgres 的 PostgresSaver（依赖 psycopg 3）。
    graph = builder.compile(checkpointer=MemorySaver())
    logger.info("Agent 图已编译：router → %s", ", ".join(WORKER_NODES))
    return graph
