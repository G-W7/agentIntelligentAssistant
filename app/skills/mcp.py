"""MCP 工具调用技能：用 ReAct 循环让 LLM 自主决定调用哪些已配置的 MCP 工具。

仅当 mcp.json 配置了至少一个 server 且 MCP_ENABLED=true 时启用；未配置时
该技能 enabled=False，不进图、不出现在路由 Prompt 中。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langgraph.prebuilt import create_react_agent

from app.config import get_settings
from app.core import mcp_client
from app.core.llm import get_chat_model
from app.skills.base import Skill, SkillMetadata

if TYPE_CHECKING:
    from app.core.agents import AgentState

logger = logging.getLogger(__name__)

# 拼接到 description 里的工具上限与单条描述截断长度；避免 Prompt 过长
_DESC_MAX_TOOLS = 30
_DESC_LINE_LIMIT = 80
_DESC_BASE = "需要调用外部工具（MCP 服务）才能完成的操作类任务。"


def _mcp_available() -> bool:
    """MCP 是否可用：开关打开且 mcp.json 配置了至少一个 server。"""
    settings = get_settings()
    return settings.mcp_enabled and bool(mcp_client.load_config())


def _render_description(tools: list[Any]) -> str:
    """把已加载的 MCP 工具拼成一段主管路由可读的 description。

    让 router_prompt() 直接看到具体工具名与简介，避免「今天是几号」这类
    问题因为 mcp 描述空泛而被误判给 search。工具过多时只保留前
    _DESC_MAX_TOOLS 个，单条描述截断到 _DESC_LINE_LIMIT 字符。
    """
    if not tools:
        return _DESC_BASE + "当前未加载任何工具。"
    lines = [_DESC_BASE, "已加载工具："]
    shown = tools[:_DESC_MAX_TOOLS]
    for tool in shown:
        name = getattr(tool, "name", "") or ""
        raw = (getattr(tool, "description", "") or "").strip().split("\n", 1)[0]
        if len(raw) > _DESC_LINE_LIMIT:
            raw = raw[:_DESC_LINE_LIMIT].rstrip() + "…"
        lines.append(f"- {name}：{raw}" if raw else f"- {name}")
    if len(tools) > len(shown):
        lines.append(f"- …（另有 {len(tools) - len(shown)} 个工具）")
    return "\n".join(lines)


def _tool_sources(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    """从 ReAct 轨迹中提取工具调用结果，整理为 sources（kind="tool"）。"""
    sources: list[dict[str, Any]] = []
    index = 0
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        index += 1
        content = (
            message.content
            if isinstance(message.content, str)
            else str(message.content)
        )
        sources.append(
            {
                "kind": "tool",
                "index": index,
                "tool_name": getattr(message, "name", "") or "",
                "content": content[:300],
            }
        )
    return sources


class McpSkill(Skill):
    """工具调用工作者：把外部 MCP server 的工具暴露给 LLM 按需调用。"""

    def __init__(self) -> None:
        self.metadata = SkillMetadata(
            name="mcp",
            label="工具调用",
            description=(
                "需要调用外部工具（文件系统、数据库、第三方 API 等 MCP 服务）"
                "才能完成的操作类任务。"
            ),
            icon="wrench",
            color="amber",
            kind="mcp",
            enabled=_mcp_available(),
        )

    async def run(self, state: "AgentState") -> dict[str, Any]:
        tools = await mcp_client.get_tools()
        if not tools:
            return {
                "messages": [AIMessage(content="MCP 未配置或暂无可用工具。")],
                "sources": [],
            }

        agent = create_react_agent(get_chat_model(), tools)
        result = await agent.ainvoke({"messages": state["messages"]})
        messages = result["messages"]
        return {"messages": [messages[-1]], "sources": _tool_sources(messages)}


skill = McpSkill()


async def warm_up() -> None:
    """启动阶段预热：拉一次 MCP 工具列表并把工具名/简介写回技能 description。

    这样主管路由 Prompt 能看到具体工具，从而把「今天几号 / 现在几点」
    这类问题正确分派到 mcp 而不是 search。失败只告警，description 保持
    静态兜底文案，不影响其它技能。
    """
    if not skill.metadata.enabled:
        return
    try:
        tools = await mcp_client.get_tools()
    except Exception:  # noqa: BLE001
        logger.warning("MCP 工具预热失败，路由 description 保持静态", exc_info=True)
        return
    skill.metadata.description = _render_description(tools)
    logger.info("MCP 路由 description 已刷新，包含 %d 个工具", len(tools))
