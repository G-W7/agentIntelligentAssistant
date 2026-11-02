"""各 Agent 节点定义：主管路由 + 三个工作者（设计文档 4.1）。

工作者采用"先确定性检索、再一次 LLM 合成"的模式，比 ReAct 循环
更快也更稳定，便于对路由准确率与引用质量做量化评估。
"""

import asyncio
import logging
from typing import Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import MessagesState
from pydantic import BaseModel, Field

from app.core.llm import get_chat_model
from app.core.tools import format_web_context, web_search
from app.services import rag_service

logger = logging.getLogger(__name__)

Destination = Literal["rag", "search", "chat"]


class AgentState(MessagesState):
    """LangGraph 全局状态。messages 由 add_messages reducer 自动累加。"""

    session_id: str
    user_id: str
    route: Destination
    route_reason: str
    sources: list[dict[str, Any]]


class RouteDecision(BaseModel):
    """主管路由的结构化输出：约束 LLM 只能返回目标工作者与一句话理由。"""

    destination: Destination = Field(description="应分发到的工作者")
    reason: str = Field(description="判断依据，一句话")


ROUTER_SYSTEM_PROMPT = """你是多 Agent 系统的主管（Supervisor），只负责判断用户问题应交给哪个工作者，不要回答问题本身。

可选工作者：
- rag：需要引用本地知识库中已上传的私有文档才能准确回答（如"根据文档…""我们的规定是…"）。
- search：具有时效性、依赖最新外部信息（如新闻、行情、天气、版本发布，或出现"今天/最近/今年"等时间词）。
- chat：闲聊、常识问答、写作、翻译、写代码等无需检索即可完成的问题。

若同时涉及内部文档与实时信息，优先选择更关键的那一个。"""

RAG_SYSTEM_PROMPT = """你是知识库问答助手，只能依据下面提供的文档片段回答。

要求：
1. 结论必须有据可依，在相应论述后用 [片段N] 标注来源。
2. 片段不足以回答时，明确说明"知识库中未找到相关内容"，禁止编造或引入外部知识。
3. 使用与用户提问相同的语言作答。

文档片段：
{context}"""

SEARCH_SYSTEM_PROMPT = """你是联网搜索助手，请依据下面的搜索结果回答。

要求：
1. 优先采用最新信息，并在相应论述后用 [N] 标注来源序号。
2. 不同来源存在冲突时，指出分歧而不是替用户下结论。
3. 搜索结果不足以回答时如实说明，不要编造。

搜索结果：
{context}"""

CHAT_SYSTEM_PROMPT = """你是一个乐于助人的智能助手，回答准确、简洁、有条理。"""


def last_human_text(messages: list[BaseMessage]) -> str:
    """倒序查找消息列表，返回最近一条用户消息的文本；没有则返回空串。"""
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


async def router_node(state: AgentState) -> dict[str, Any]:
    """主管节点：让 LLM 以结构化输出判定问题应分发给哪个工作者。

    只负责路由决策，不回答问题本身；结果写入 state 的 route / route_reason。
    """
    query = last_human_text(state["messages"])
    structured = get_chat_model().with_structured_output(
        RouteDecision, method="function_calling"
    )
    decision = await structured.ainvoke(
        [
            SystemMessage(content=ROUTER_SYSTEM_PROMPT),
            HumanMessage(content=query),
        ]
    )
    logger.info("路由判定 → %s：%s", decision.destination, decision.reason)
    return {"route": decision.destination, "route_reason": decision.reason}


async def rag_worker(state: AgentState) -> dict[str, Any]:
    """知识库工作者：向量检索本地知识库 → LLM 基于片段合成回答。

    检索无命中时直接回复"未检索到"，不调 LLM；
    命中时把片段拼入系统 Prompt，要求回答标注 [片段N] 来源，
    并把命中片段整理为 sources 返回给前端展示。
    """
    query = last_human_text(state["messages"])
    # 仅检索当前登录用户自己的知识库文档
    hits = await asyncio.to_thread(
        rag_service.retrieve_chunks, query, state["user_id"]
    )

    if not hits:
        answer = "知识库中未检索到与该问题相关的内容。请先上传相关文档，或换一种问法。"
        return {"messages": [AIMessage(content=answer)], "sources": []}

    prompt = RAG_SYSTEM_PROMPT.format(context=rag_service.format_context(hits))
    response = await get_chat_model().ainvoke(
        [SystemMessage(content=prompt), *state["messages"]]
    )
    sources = [
        {
            "kind": "knowledge",
            "file_id": hit.source_file_id,
            "page": hit.page,
            "score": round(hit.score, 4),
            "content": hit.content[:300],
        }
        for hit in hits
    ]
    return {"messages": [response], "sources": sources}


async def search_worker(state: AgentState) -> dict[str, Any]:
    """搜索工作者：Tavily 联网搜索 → LLM 基于搜索结果合成回答。

    搜索异常或无结果时降级为直接文字回复，不调 LLM；
    正常时把带编号的搜索结果拼入 Prompt，要求回答标注 [N] 引用，
    sources 中携带每条结果的标题 / URL / 分数。
    """
    query = last_human_text(state["messages"])

    try:
        outcome = await asyncio.to_thread(web_search, query)
    except Exception as exc:
        logger.exception("联网搜索失败")
        answer = f"联网搜索暂时不可用：{exc}"
        return {"messages": [AIMessage(content=answer)], "sources": []}

    if not outcome.results:
        answer = "没有找到相关的搜索结果，可以尝试换一种表述。"
        return {"messages": [AIMessage(content=answer)], "sources": []}

    prompt = SEARCH_SYSTEM_PROMPT.format(context=format_web_context(outcome))
    response = await get_chat_model().ainvoke(
        [SystemMessage(content=prompt), *state["messages"]]
    )
    sources = [
        {
            "kind": "web",
            "index": index,
            "title": item.title,
            "url": item.url,
            "score": round(item.score, 4),
            "content": item.content[:300],
        }
        for index, item in enumerate(outcome.results, start=1)
    ]
    return {"messages": [response], "sources": sources}


async def chat_worker(state: AgentState) -> dict[str, Any]:
    """闲聊工作者：无需检索，直接带通用系统 Prompt 调 LLM 回答，sources 为空。"""
    response = await get_chat_model().ainvoke(
        [SystemMessage(content=CHAT_SYSTEM_PROMPT), *state["messages"]]
    )
    return {"messages": [response], "sources": []}
