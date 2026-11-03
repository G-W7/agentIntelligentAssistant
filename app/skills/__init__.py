"""可插拔技能包。

- base：技能契约（Skill / SkillMetadata）；
- registry：技能发现与注册中心。

具体技能模块（rag / search / chat / mcp 及用户自定义）由 registry.discover()
在运行时动态导入，不在此处 eager import，以避免与 app.core.agents 形成导入环。
"""

from app.skills.base import Skill, SkillMetadata
from app.skills import registry

__all__ = ["Skill", "SkillMetadata", "registry"]
