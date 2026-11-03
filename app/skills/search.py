"""联网搜索技能（内置）：Tavily 联网搜索 → LLM 基于搜索结果合成回答。

由 app/core/agents.py 的 search_worker 迁移而来，行为保持一致：
搜索异常或无结果时降级为直接文字回复，不调 LLM；正常时把带编号的搜索结果
拼入 Prompt，要求回答标注 [N] 引用，sources 中携带每条结果的标题 / URL / 分数。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, SystemMessage

from app.core.agents import last_human_text
from app.core.llm import get_chat_model
from app.core.tools import format_web_context, web_search
from app.skills.base import Skill, SkillMetadata

if TYPE_CHECKING:
    from app.core.agents import AgentState

logger = logging.getLogger(__name__)

SEARCH_SYSTEM_PROMPT = """你是联网搜索助手，请依据下面的搜索结果回答。

要求：
1. 优先采用最新信息，并在相应论述后用 [N] 标注来源序号。
2. 不同来源存在冲突时，指出分歧而不是替用户下结论。
3. 搜索结果不足以回答时如实说明，不要编造。

搜索结果：
{context}"""


class SearchSkill(Skill):
    """搜索工作者：调用 Tavily 获取实时外部信息。"""

    metadata = SkillMetadata(
        name="search",
        label="联网搜索",
        description=(
            "具有时效性、依赖最新外部信息（如新闻、行情、天气、版本发布，"
            "或出现“今天/最近/今年”等时间词）。"
        ),
        icon="search",
        color="sky",
        kind="builtin",
    )

    async def run(self, state: "AgentState") -> dict[str, Any]:
        query = last_human_text(state["messages"])

        try:
            outcome = await asyncio.to_thread(web_search, query)
        except Exception as exc:  # noqa: BLE001
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


skill = SearchSkill()
