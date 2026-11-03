"""知识库问答技能（内置）：向量检索本地知识库 → LLM 基于片段合成回答。

由 app/core/agents.py 的 rag_worker 迁移而来，行为保持一致：
检索无命中时直接回复"未检索到"，不调 LLM；命中时把片段拼入系统 Prompt，
要求回答标注 [片段N] 来源，并把命中片段整理为 sources 返回给前端展示。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, SystemMessage

from app.core.agents import last_human_text
from app.core.llm import get_chat_model
from app.services import rag_service
from app.skills.base import Skill, SkillMetadata

if TYPE_CHECKING:
    from app.core.agents import AgentState

logger = logging.getLogger(__name__)

RAG_SYSTEM_PROMPT = """你是知识库问答助手，只能依据下面提供的文档片段回答。

要求：
1. 结论必须有据可依，在相应论述后用 [片段N] 标注来源。
2. 片段不足以回答时，明确说明"知识库中未找到相关内容"，禁止编造或引入外部知识。
3. 使用与用户提问相同的语言作答。

文档片段：
{context}"""


class RagSkill(Skill):
    """知识库工作者：仅检索当前登录用户自己的知识库文档。"""

    metadata = SkillMetadata(
        name="rag",
        label="知识库",
        description=(
            "需要引用本地知识库中已上传的私有文档才能准确回答"
            "（如“根据文档…”“我们的规定是…”）。"
        ),
        icon="book-open",
        color="emerald",
        kind="builtin",
    )

    async def run(self, state: "AgentState") -> dict[str, Any]:
        query = last_human_text(state["messages"])
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


skill = RagSkill()
