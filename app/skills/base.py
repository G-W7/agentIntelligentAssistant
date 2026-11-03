"""技能契约：所有可插拔工作者实现统一的 Skill 接口。

一个技能 = 图中的一个工作者节点。约定每个技能模块暴露一个模块级
`skill` 变量（Skill 实例），由 registry.discover() 自动发现并注册。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # 仅类型检查期导入，避免与 app.core.agents 形成运行时导入环
    from app.core.agents import AgentState


@dataclass
class SkillMetadata:
    """技能元数据。

    name 同时作为路由目标（RouteDecision.destination）与图节点名，必须全局唯一；
    label / icon / color 供前端展示；description 会被写入主管的动态路由 Prompt，
    决定 LLM 何时把问题分发到该技能。
    """

    name: str
    label: str
    description: str
    icon: str = "sparkles"  # 前端 lucide 图标名（kebab-case）
    color: str = "violet"  # 前端徽章配色 key
    kind: str = "custom"  # builtin | custom | mcp
    enabled: bool = True


class Skill(ABC):
    """可插拔工作者基类。

    子类需：
    1. 提供 `metadata`（SkillMetadata 实例）；
    2. 实现 `async run(state)`，返回状态增量 {"messages": [...], "sources": [...]}；
    3. 在模块末尾暴露 `skill = XxxSkill()`。
    """

    metadata: SkillMetadata

    @abstractmethod
    async def run(self, state: "AgentState") -> dict[str, Any]:
        """执行技能逻辑，返回写回 LangGraph 状态的增量字典。"""
        raise NotImplementedError
