"""主管路由节点与全局状态定义（设计文档 4.1）。

具体的工作者逻辑已下沉到 app/skills/ 下的各技能模块，由注册表在运行时
动态发现并注册为图节点；本模块只保留状态、路由决策模型与主管节点。
"""

import logging
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import MessagesState
from pydantic import BaseModel, Field

from app.core.llm import get_chat_model
from app.skills import registry

logger = logging.getLogger(__name__)

# 路由目标不再写死为固定字面量：可选值由技能注册表在运行时决定。
# 保留 str 别名以兼容既有的类型标注与导入。
Destination = str


class AgentState(MessagesState):
    """LangGraph 全局状态。messages 由 add_messages reducer 自动累加。"""

    session_id: str
    user_id: str
    route: Destination
    route_reason: str
    sources: list[dict[str, Any]]


class RouteDecision(BaseModel):
    """主管路由的结构化输出：约束 LLM 只能返回目标工作者与一句话理由。"""

    destination: Destination = Field(description="应分发到的工作者名称")
    reason: str = Field(description="判断依据，一句话")


def last_human_text(messages: list[BaseMessage]) -> str:
    """倒序查找消息列表，返回最近一条用户消息的文本；没有则返回空串。"""
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


async def router_node(state: AgentState) -> dict[str, Any]:
    """主管节点：让 LLM 以结构化输出判定问题应分发给哪个工作者。

    只负责路由决策，不回答问题本身；可选工作者列表由技能注册表动态生成，
    结果写入 state 的 route / route_reason。
    """
    query = last_human_text(state["messages"])
    structured = get_chat_model().with_structured_output(
        RouteDecision, method="function_calling"
    )
    decision = await structured.ainvoke(
        [
            SystemMessage(content=registry.router_prompt()),
            HumanMessage(content=query),
        ]
    )
    logger.info("路由判定 → %s：%s", decision.destination, decision.reason)
    return {"route": decision.destination, "route_reason": decision.reason}
