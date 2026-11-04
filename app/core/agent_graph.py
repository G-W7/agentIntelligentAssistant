"""LangGraph 编排：主管-工作者拓扑，工作者由技能注册表动态提供（设计文档 4.1、8）。

拓扑：START → router →(条件分发 route_decision)→ 各已启用技能 → END。
技能在 app/skills/ 下以文件形式定义，registry.discover() 负责发现；
新增 / 修改技能文件后重启服务即可生效（图仍 lru_cache 只编译一次）。
"""

import logging
from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.core.agents import AgentState, router_node
from app.db.checkpointer import get_checkpointer
from app.skills import registry

logger = logging.getLogger(__name__)


def get_worker_nodes() -> dict[str, str]:
    """路由目标 → 工作者节点名的映射，由已启用的技能动态生成。

    同时作为条件边的分支表。延迟求值：确保技能注册表已 discover。
    """
    return registry.worker_nodes()


def route_decision(state: AgentState) -> str:
    """条件边：把主管给出的 destination 映射到工作者节点名，未知目标兜底到 chat。"""
    return get_worker_nodes().get(state.get("route", "chat"), "chat")


@lru_cache
def get_graph() -> Any:
    """构建并缓存 LangGraph 图（进程内只编译一次）。

    先触发技能发现，再据注册表动态注册 router 与各工作者节点。
    """
    registry.discover()
    nodes = get_worker_nodes()

    builder = StateGraph(AgentState)
    builder.add_node("router", router_node)
    for name in nodes:
        builder.add_node(name, registry.get(name).run)

    builder.add_edge(START, "router")
    builder.add_conditional_edges("router", route_decision, nodes)
    for node in nodes.values():
        builder.add_edge(node, END)

    # Checkpointer 由 app.db.checkpointer 统一提供：默认 AsyncPostgresSaver，把会话
    # 状态持久化到 PostgreSQL，使多进程 / 多实例部署时同一 thread 落到任意实例都能
    # 恢复多轮上下文；PostgreSQL 不可用时回退进程内 MemorySaver（仅单实例、重启丢失）。
    # 跨重启的持久化记忆与前端展示仍由 chat_history 兜底（见 chat_service）。
    graph = builder.compile(checkpointer=get_checkpointer())
    logger.info("Agent 图已编译：router → %s", ", ".join(nodes))
    return graph
