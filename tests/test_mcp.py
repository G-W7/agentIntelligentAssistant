"""MCP 接入测试：配置加载、启用判定、工具连接与 McpSkill.run() 的来源生成。

全部用受控的临时 mcp.json + monkeypatch 完成，不真正启动任何 MCP server：
- load_config()：文件缺失 / 正常解析 / 非法 JSON / 缺 mcpServers 键；
- _mcp_available() 与 McpSkill.enabled：随配置与开关变化；
- get_tools()：mock MultiServerMCPClient，验证连接、缓存与异常降级；
- McpSkill.run()：无工具降级、有工具经 mock ReAct 代理生成 kind="tool" 来源；
- _tool_sources()：截断、编号与非字符串 content 容错。
"""

from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core import mcp_client
from app.skills import mcp


@pytest.fixture(autouse=True)
def _reset_tools_cache():
    """每个用例前后清空进程内工具缓存，避免相互串扰。"""
    mcp_client.reset_cache()
    yield
    mcp_client.reset_cache()


@pytest.fixture
def mcp_config(monkeypatch, make_settings, tmp_path):
    """写入受控 mcp.json，并把 mcp_client / mcp 两处 get_settings 指向它。

    text=None 表示不创建文件（模拟未配置）。
    """

    def _apply(text=None, *, mcp_enabled=True):
        path = tmp_path / "mcp.json"
        if text is not None:
            path.write_text(text, encoding="utf-8")
        settings = make_settings(mcp_enabled=mcp_enabled, mcp_config_path=path)
        monkeypatch.setattr(mcp_client, "get_settings", lambda: settings)
        monkeypatch.setattr(mcp, "get_settings", lambda: settings)
        return path

    return _apply


# ---------- load_config ----------


def test_load_config_missing_file_returns_empty(mcp_config):
    mcp_config(None)
    assert mcp_client.load_config() == {}


def test_load_config_parses_servers(mcp_config):
    mcp_config('{"mcpServers": {"fs": {"command": "npx", "args": ["-y"]}}}')
    assert mcp_client.load_config() == {"fs": {"command": "npx", "args": ["-y"]}}


def test_load_config_invalid_json_returns_empty(mcp_config):
    mcp_config("{ 这不是合法 JSON")
    assert mcp_client.load_config() == {}


def test_load_config_missing_mcp_servers_key_returns_empty(mcp_config):
    mcp_config('{"other": 1}')
    assert mcp_client.load_config() == {}


def test_load_config_non_dict_servers_returns_empty(mcp_config):
    mcp_config('{"mcpServers": "应为对象却是字符串"}')
    assert mcp_client.load_config() == {}


def test_list_servers_returns_names(mcp_config):
    mcp_config('{"mcpServers": {"a": {}, "b": {}}}')
    assert mcp_client.list_servers() == ["a", "b"]


# ---------- _mcp_available / McpSkill.enabled ----------


def test_mcp_available_false_without_config(mcp_config):
    mcp_config(None)
    assert mcp._mcp_available() is False


def test_mcp_available_true_with_config(mcp_config):
    mcp_config('{"mcpServers": {"fs": {}}}')
    assert mcp._mcp_available() is True


def test_mcp_available_false_when_disabled(mcp_config):
    mcp_config('{"mcpServers": {"fs": {}}}', mcp_enabled=False)
    assert mcp._mcp_available() is False


def test_mcp_skill_disabled_without_config(mcp_config):
    mcp_config(None)
    assert mcp.McpSkill().metadata.enabled is False


def test_mcp_skill_enabled_with_config(mcp_config):
    mcp_config('{"mcpServers": {"fs": {}}}')
    skill = mcp.McpSkill()
    assert skill.metadata.enabled is True
    assert skill.metadata.name == "mcp"
    assert skill.metadata.kind == "mcp"


# ---------- get_tools ----------


async def test_get_tools_without_config_returns_empty(mcp_config):
    mcp_config(None)
    assert await mcp_client.get_tools() == []


async def test_get_tools_connects_once_and_caches(mcp_config, monkeypatch):
    mcp_config('{"mcpServers": {"fs": {"command": "npx"}}}')
    fake_tool = SimpleNamespace(name="read_file", description="读取文件")
    calls = {"connect": 0}

    class FakeClient:
        def __init__(self, config):
            self.config = config

        async def get_tools(self):
            calls["connect"] += 1
            return [fake_tool]

    monkeypatch.setattr(
        "langchain_mcp_adapters.client.MultiServerMCPClient", FakeClient
    )

    first = await mcp_client.get_tools()
    second = await mcp_client.get_tools()
    assert first == [fake_tool]
    assert second == [fake_tool]
    # 命中缓存：只连接一次
    assert calls["connect"] == 1


async def test_get_tools_exception_degrades_to_empty(mcp_config, monkeypatch):
    mcp_config('{"mcpServers": {"fs": {"command": "npx"}}}')

    class BoomClient:
        def __init__(self, config):
            raise RuntimeError("连接失败")

    monkeypatch.setattr(
        "langchain_mcp_adapters.client.MultiServerMCPClient", BoomClient
    )
    assert await mcp_client.get_tools() == []


# ---------- McpSkill.run ----------


async def test_run_without_tools_degrades(monkeypatch):
    async def no_tools():
        return []

    monkeypatch.setattr(mcp.mcp_client, "get_tools", no_tools)
    result = await mcp.McpSkill().run({"messages": [HumanMessage(content="列出文件")]})

    assert isinstance(result["messages"][0], AIMessage)
    assert "MCP 未配置" in result["messages"][0].content
    assert result["sources"] == []


async def test_run_with_tools_builds_tool_sources(monkeypatch):
    fake_tool = SimpleNamespace(name="read_file", description="读取文件")

    async def one_tool():
        return [fake_tool]

    monkeypatch.setattr(mcp.mcp_client, "get_tools", one_tool)
    monkeypatch.setattr(mcp, "get_chat_model", lambda: object())

    tool_msg = ToolMessage(content="文件内容ABC", tool_call_id="1", name="read_file")
    final = AIMessage(content="已读取文件")
    captured = {}

    class FakeAgent:
        async def ainvoke(self, payload):
            captured["payload"] = payload
            return {"messages": [payload["messages"][0], tool_msg, final]}

    def fake_create_react_agent(model, tools):
        captured["tools"] = tools
        return FakeAgent()

    monkeypatch.setattr(mcp, "create_react_agent", fake_create_react_agent)

    question = HumanMessage(content="读取 a.txt")
    result = await mcp.McpSkill().run({"messages": [question]})

    assert captured["tools"] == [fake_tool]
    assert captured["payload"]["messages"] == [question]
    # 只回传轨迹最后一条 AIMessage
    assert result["messages"] == [final]
    sources = result["sources"]
    assert len(sources) == 1
    assert sources[0]["kind"] == "tool"
    assert sources[0]["index"] == 1
    assert sources[0]["tool_name"] == "read_file"
    assert sources[0]["content"] == "文件内容ABC"


# ---------- _tool_sources ----------


def test_tool_sources_indexes_and_truncates():
    messages = [
        HumanMessage(content="q"),
        ToolMessage(content="x" * 400, tool_call_id="1", name="tool_a"),
        AIMessage(content="中间步骤"),
        ToolMessage(content="短结果", tool_call_id="2", name="tool_b"),
    ]
    sources = mcp._tool_sources(messages)
    assert len(sources) == 2
    assert sources[0]["index"] == 1
    assert sources[0]["tool_name"] == "tool_a"
    assert len(sources[0]["content"]) == 300  # 截断到 300
    assert sources[1]["index"] == 2
    assert sources[1]["tool_name"] == "tool_b"
    assert sources[1]["content"] == "短结果"


def test_tool_sources_ignores_non_tool_messages():
    messages = [HumanMessage(content="q"), AIMessage(content="a")]
    assert mcp._tool_sources(messages) == []


def test_tool_sources_stringifies_non_str_content():
    messages = [ToolMessage(content=[{"type": "text"}], tool_call_id="1", name="t")]
    sources = mcp._tool_sources(messages)
    assert isinstance(sources[0]["content"], str)


# ---------- _render_description / warm_up ----------


def test_render_description_empty_tools_returns_base_text():
    text = mcp._render_description([])
    assert "当前未加载任何工具" in text
    assert "已加载工具" not in text


def test_render_description_lists_names_and_first_line_only():
    tools = [
        SimpleNamespace(
            name="get_current_time",
            description="Get current time in a specific timezone\n忽略的第二行",
        ),
        SimpleNamespace(name="convert_time", description="Convert time between timezones"),
    ]
    text = mcp._render_description(tools)
    assert "- get_current_time：Get current time in a specific timezone" in text
    assert "- convert_time：Convert time between timezones" in text
    assert "忽略的第二行" not in text


def test_render_description_truncates_long_line():
    tools = [SimpleNamespace(name="t", description="x" * 200)]
    text = mcp._render_description(tools)
    # 单行描述被截断到 _DESC_LINE_LIMIT 字符 + 省略号
    assert "…" in text
    assert "x" * (mcp._DESC_LINE_LIMIT + 1) not in text


def test_render_description_caps_tool_count():
    tools = [
        SimpleNamespace(name=f"tool_{i}", description=f"desc {i}")
        for i in range(mcp._DESC_MAX_TOOLS + 5)
    ]
    text = mcp._render_description(tools)
    assert f"tool_{mcp._DESC_MAX_TOOLS - 1}" in text
    assert f"tool_{mcp._DESC_MAX_TOOLS}" not in text
    assert "另有 5 个工具" in text


def test_render_description_handles_tool_without_description():
    text = mcp._render_description([SimpleNamespace(name="bare", description="")])
    assert "- bare" in text


async def test_warm_up_updates_skill_description(mcp_config, monkeypatch):
    mcp_config('{"mcpServers": {"time": {"command": "uv"}}}')
    # 刷新 enabled（McpSkill 已在模块加载时构造，需重新指向新 settings）
    monkeypatch.setattr(mcp.skill.metadata, "enabled", True)

    fake_tools = [
        SimpleNamespace(name="get_current_time", description="Get current time"),
        SimpleNamespace(name="convert_time", description="Convert time"),
    ]

    async def fake_get_tools():
        return fake_tools

    monkeypatch.setattr(mcp.mcp_client, "get_tools", fake_get_tools)
    original = mcp.skill.metadata.description
    try:
        await mcp.warm_up()
        assert "get_current_time" in mcp.skill.metadata.description
        assert "convert_time" in mcp.skill.metadata.description
        assert mcp.skill.metadata.description != original
    finally:
        mcp.skill.metadata.description = original


async def test_warm_up_noop_when_disabled(mcp_config, monkeypatch):
    mcp_config('{"mcpServers": {"time": {"command": "uv"}}}')
    monkeypatch.setattr(mcp.skill.metadata, "enabled", False)

    called = {"hit": False}

    async def fake_get_tools():
        called["hit"] = True
        return []

    monkeypatch.setattr(mcp.mcp_client, "get_tools", fake_get_tools)
    original = mcp.skill.metadata.description
    try:
        await mcp.warm_up()
        assert called["hit"] is False
        assert mcp.skill.metadata.description == original
    finally:
        mcp.skill.metadata.description = original


async def test_warm_up_swallows_exceptions(mcp_config, monkeypatch):
    mcp_config('{"mcpServers": {"time": {"command": "uv"}}}')
    monkeypatch.setattr(mcp.skill.metadata, "enabled", True)

    async def boom():
        raise RuntimeError("连接失败")

    monkeypatch.setattr(mcp.mcp_client, "get_tools", boom)
    original = mcp.skill.metadata.description
    try:
        # 不抛异常，description 保持原样
        await mcp.warm_up()
        assert mcp.skill.metadata.description == original
    finally:
        mcp.skill.metadata.description = original
