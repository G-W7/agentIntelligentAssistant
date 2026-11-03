"""通用对话技能（内置）：无需检索，直接带通用系统 Prompt 调 LLM 回答。

由 app/core/agents.py 的 chat_worker 迁移而来，同时作为路由兜底技能：
当主管给出的目标不在注册表中时，条件边会回退到 chat。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langchain_core.messages import SystemMessage

from app.core.llm import get_chat_model
from app.skills.base import Skill, SkillMetadata

if TYPE_CHECKING:
    from app.core.agents import AgentState

logger = logging.getLogger(__name__)

CHAT_SYSTEM_PROMPT = """你是一个乐于助人的智能助手，回答准确、简洁、有条理。"""


class ChatSkill(Skill):
    """闲聊工作者：常识问答、写作、翻译、写代码等无需检索的问题。"""

    metadata = SkillMetadata(
        name="chat",
        label="通用对话",
        description="闲聊、常识问答、写作、翻译、写代码等无需检索即可完成的问题。",
        icon="message-square",
        color="violet",
        kind="builtin",
    )

    async def run(self, state: "AgentState") -> dict[str, Any]:
        response = await get_chat_model().ainvoke(
            [SystemMessage(content=CHAT_SYSTEM_PROMPT), *state["messages"]]
        )
        return {"messages": [response], "sources": []}


skill = ChatSkill()
