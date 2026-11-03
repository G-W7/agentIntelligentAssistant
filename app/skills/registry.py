"""技能注册表：自动发现 app/skills/ 下的技能模块并统一注册。

约定：每个技能模块暴露一个模块级 `skill` 变量（Skill 实例）。
discover() 幂等，首次调用时扫描并导入所有技能模块；各读取接口内部
都会先确保 discover() 已执行，因此调用方无需关心发现时机。
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from pathlib import Path

from app.skills.base import Skill

logger = logging.getLogger(__name__)

_PACKAGE_DIR = Path(__file__).resolve().parent
# 基础设施模块，不作为技能扫描
_SKIP_MODULES = {"base", "registry"}

_REGISTRY: dict[str, Skill] = {}
_discovered = False

_ROUTER_HEADER = (
    "你是多 Agent 系统的主管（Supervisor），只负责判断用户问题应交给哪个工作者，"
    "不要回答问题本身。\n\n可选工作者：\n"
)
_ROUTER_FOOTER = (
    "\n\n若同时涉及多个工作者，优先选择更关键的那一个。"
    "destination 只能从上述工作者名称中选择一个。"
)


def register(skill: Skill) -> None:
    """注册一个技能；name 为空或重复时告警并跳过（保留先注册者）。"""
    name = skill.metadata.name
    if not name:
        logger.warning("技能 name 为空，跳过注册")
        return
    if name in _REGISTRY:
        logger.warning("技能 %r 已存在，跳过重复注册", name)
        return
    _REGISTRY[name] = skill
    logger.debug(
        "注册技能 %r（kind=%s, enabled=%s）",
        name,
        skill.metadata.kind,
        skill.metadata.enabled,
    )


def discover() -> None:
    """扫描并导入 app/skills/ 下的技能模块，注册其 `skill` 实例。幂等。

    单个模块导入失败只告警跳过，不影响其它技能与整体启动。
    """
    global _discovered
    if _discovered:
        return
    for module_info in pkgutil.iter_modules([str(_PACKAGE_DIR)]):
        name = module_info.name
        if name in _SKIP_MODULES or name.startswith("_"):
            continue
        try:
            module = importlib.import_module(f"app.skills.{name}")
        except Exception:  # noqa: BLE001
            logger.exception("导入技能模块 app.skills.%s 失败，已跳过", name)
            continue
        skill = getattr(module, "skill", None)
        if isinstance(skill, Skill):
            register(skill)
        else:
            logger.debug("模块 app.skills.%s 未暴露 Skill 实例，跳过", name)
    _discovered = True
    logger.info(
        "技能发现完成：共 %d 个，启用 %d 个", len(_REGISTRY), len(all_skills())
    )


def get(name: str) -> Skill | None:
    """按 name 取技能实例（含未启用的），不存在返回 None。"""
    discover()
    return _REGISTRY.get(name)


def all_skills(include_disabled: bool = False) -> list[Skill]:
    """返回技能列表（默认仅启用的），按 name 稳定排序。"""
    discover()
    skills = list(_REGISTRY.values())
    if not include_disabled:
        skills = [s for s in skills if s.metadata.enabled]
    return sorted(skills, key=lambda s: s.metadata.name)


def worker_nodes() -> dict[str, str]:
    """启用技能的「路由目标 → 图节点名」映射，供图构建与条件边使用。"""
    return {s.metadata.name: s.metadata.name for s in all_skills()}


def router_prompt() -> str:
    """用各启用技能的 description 动态拼装主管系统 Prompt。"""
    lines = [
        f"- {s.metadata.name}：{s.metadata.description}" for s in all_skills()
    ]
    return _ROUTER_HEADER + "\n".join(lines) + _ROUTER_FOOTER


def reset() -> None:
    """清空注册表与发现标记（仅测试用）。"""
    global _discovered
    _REGISTRY.clear()
    _discovered = False
