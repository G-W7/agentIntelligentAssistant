"""Agent 编排纯逻辑测试：路由分发 route_decision 与 last_human_text。

不触发 LLM，只验证图的条件边映射与"取最近一条用户消息"的工具函数。
"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.core.agent_graph import get_worker_nodes, route_decision
from app.core.agents import last_human_text


# ---------- route_decision ----------


def test_route_decision_maps_known_destinations():
    assert route_decision({"route": "rag"}) == "rag"
    assert route_decision({"route": "search"}) == "search"
    assert route_decision({"route": "chat"}) == "chat"


def test_route_decision_unknown_falls_back_to_chat():
    assert route_decision({"route": "whatever"}) == "chat"


def test_route_decision_missing_route_defaults_chat():
    # state 未带 route 时应回退到 chat
    assert route_decision({}) == "chat"


def test_worker_nodes_covers_all_destinations():
    # 工作者由技能注册表动态生成；内置三技能必然在列，mcp 视配置而定。
    assert set(get_worker_nodes()) >= {"rag", "search", "chat"}


# ---------- last_human_text ----------


def test_last_human_text_returns_latest_user_message():
    messages = [
        HumanMessage(content="第一条"),
        AIMessage(content="回复"),
        HumanMessage(content="最新一条"),
    ]
    assert last_human_text(messages) == "最新一条"


def test_last_human_text_ignores_non_human():
    messages = [SystemMessage(content="系统"), AIMessage(content="助手")]
    assert last_human_text(messages) == ""


def test_last_human_text_empty_list():
    assert last_human_text([]) == ""
