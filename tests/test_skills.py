"""技能注册表测试：自动发现、动态路由 Prompt、注册规则与「放文件即注册」约定。

覆盖 app/skills/registry.py 的纯逻辑（不触发 LLM）：
- discover() 能发现内置三技能（rag/search/chat）；
- router_prompt() 用各启用技能的 description 动态拼装；
- register() 对空名 / 重名跳过；
- get()/all_skills()/worker_nodes() 的启用过滤行为；
- 往 app/skills/ 放一个符合约定的 .py，reset+discover 后即被注册。
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from app.skills import registry
from app.skills.base import Skill, SkillMetadata

_SKILLS_DIR = Path(registry.__file__).resolve().parent


@pytest.fixture(autouse=True)
def _fresh_registry():
    """每个用例前后重置并重新发现，保证注册表状态隔离、可复现。"""
    registry.reset()
    registry.discover()
    yield
    registry.reset()
    registry.discover()


class _DummySkill(Skill):
    """用于注册规则测试的最小技能实现。"""

    def __init__(self, name, description="占位描述", enabled=True, kind="custom"):
        self.metadata = SkillMetadata(
            name=name,
            label=name or "空",
            description=description,
            kind=kind,
            enabled=enabled,
        )

    async def run(self, state):
        return {"messages": [], "sources": []}


# ---------- discover / all_skills / worker_nodes ----------


def test_discover_registers_builtin_skills():
    names = {s.metadata.name for s in registry.all_skills()}
    assert names >= {"rag", "search", "chat"}


def test_discover_is_idempotent():
    before = {s.metadata.name for s in registry.all_skills()}
    registry.discover()  # 再次调用不应改变结果，也不应重复注册
    after = {s.metadata.name for s in registry.all_skills()}
    assert before == after


def test_worker_nodes_maps_enabled_skills_to_themselves():
    nodes = registry.worker_nodes()
    assert nodes["rag"] == "rag"
    assert set(nodes) >= {"rag", "search", "chat"}


def test_all_skills_sorted_by_name():
    names = [s.metadata.name for s in registry.all_skills()]
    assert names == sorted(names)


# ---------- router_prompt ----------


def test_router_prompt_lists_every_enabled_skill():
    prompt = registry.router_prompt()
    assert "可选工作者" in prompt
    for s in registry.all_skills():
        assert s.metadata.name in prompt
        assert s.metadata.description in prompt


def test_router_prompt_excludes_disabled_skill():
    registry.register(_DummySkill("off_skill", enabled=False))
    prompt = registry.router_prompt()
    assert "off_skill" not in prompt
    # include_disabled 时才出现在列表中
    assert "off_skill" in {s.metadata.name for s in registry.all_skills(True)}


# ---------- register 规则 ----------


def test_register_skips_duplicate_name():
    original = registry.get("rag")
    registry.register(_DummySkill("rag", description="冒名顶替"))
    # 重名应保留先注册者，不被覆盖
    assert registry.get("rag") is original
    assert registry.get("rag").metadata.description != "冒名顶替"


def test_register_skips_empty_name():
    count_before = len(registry.all_skills(include_disabled=True))
    registry.register(_DummySkill(""))
    count_after = len(registry.all_skills(include_disabled=True))
    assert count_before == count_after
    assert registry.get("") is None


def test_get_unknown_returns_none():
    assert registry.get("不存在的技能") is None


def test_disabled_skill_not_in_worker_nodes():
    registry.register(_DummySkill("disabled_one", enabled=False))
    assert "disabled_one" not in registry.worker_nodes()
    assert registry.get("disabled_one") is not None  # get 仍能取到（含未启用）


# ---------- 「放文件即注册」约定 ----------


def test_dropping_skill_file_registers_after_discover():
    """往 app/skills/ 放一个暴露 `skill` 的模块，reset+discover 后自动注册。"""
    module_name = "tmp_probe_skill"
    file_path = _SKILLS_DIR / f"{module_name}.py"
    file_path.write_text(
        "from app.skills.base import Skill, SkillMetadata\n"
        "\n"
        "\n"
        "class TmpProbeSkill(Skill):\n"
        "    metadata = SkillMetadata(\n"
        "        name='tmp_probe',\n"
        "        label='临时探针',\n"
        "        description='用于验证放文件即注册的约定',\n"
        "        kind='custom',\n"
        "    )\n"
        "\n"
        "    async def run(self, state):\n"
        "        return {'messages': [], 'sources': []}\n"
        "\n"
        "\n"
        "skill = TmpProbeSkill()\n",
        encoding="utf-8",
    )
    try:
        registry.reset()
        registry.discover()
        assert registry.get("tmp_probe") is not None
        assert "tmp_probe" in registry.worker_nodes()
        assert "放文件即注册" in registry.router_prompt()
    finally:
        # 彻底清理：删源文件、删编译缓存、移出 sys.modules、恢复注册表，
        # 避免遗留的 .pyc 或模块污染后续用例与生产环境
        file_path.unlink(missing_ok=True)
        Path(importlib.util.cache_from_source(file_path)).unlink(missing_ok=True)
        sys.modules.pop(f"app.skills.{module_name}", None)
        registry.reset()
        registry.discover()
