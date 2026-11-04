"""app/services/chat_service.py 的单元测试。

只覆盖不触发真实 Agent 图 / PostgreSQL 的部分：
- _text_of：字符串与多模态分块两种 content 形态；
- _load_history：把数据库行还原为 LangChain 消息对象（mock pg_client）；
- _prepare_session：根据 checkpoint 是否存在决定是否灌历史 seed（mock 图与 pg_client）；
- history / delete_session / list_sessions：透传层（mock pg_client / checkpointer）。
"""

from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage

from app.services import chat_service
from app.services.chat_service import _text_of


# ---------- _text_of ----------


def test_text_of_plain_string():
    assert _text_of(AIMessage(content="纯文本回答")) == "纯文本回答"


def test_text_of_multimodal_parts():
    message = AIMessage(
        content=[{"type": "text", "text": "片段一"}, {"type": "text", "text": "片段二"}]
    )
    assert _text_of(message) == "片段一片段二"


def test_text_of_ignores_non_dict_parts():
    # content 列表允许 str 或 dict；非 dict 的 str 项不贡献文本
    message = AIMessage(content=[{"text": "保留"}, "字符串项被忽略"])
    assert _text_of(message) == "保留"


# ---------- _load_history ----------


def test_load_history_maps_roles_to_message_classes(monkeypatch, fake_history_rows):
    captured = {}

    def fake_list_messages(session_id, user_id, limit=None):
        captured["args"] = (session_id, user_id, limit)
        return fake_history_rows

    monkeypatch.setattr(chat_service.pg_client, "list_messages", fake_list_messages)

    messages = chat_service._load_history("s1", "u1")

    assert [type(m) for m in messages] == [HumanMessage, AIMessage, HumanMessage]
    assert [m.content for m in messages] == ["你好", "你好，有什么可以帮你？", "介绍一下 RAG"]
    # 确认按 user_id 隔离查询
    assert captured["args"][0] == "s1"
    assert captured["args"][1] == "u1"


def test_load_history_skips_unknown_roles(monkeypatch):
    rows = [
        {"role": "user", "content": "hi"},
        {"role": "system", "content": "应被忽略"},
        {"role": "assistant", "content": "hello"},
    ]
    monkeypatch.setattr(chat_service.pg_client, "list_messages", lambda *a, **k: rows)

    messages = chat_service._load_history("s1", "u1")
    # system 角色不在映射表内，应被跳过
    assert len(messages) == 2
    assert all(isinstance(m, (HumanMessage, AIMessage)) for m in messages)


def test_load_history_empty(monkeypatch):
    monkeypatch.setattr(chat_service.pg_client, "list_messages", lambda *a, **k: [])
    assert chat_service._load_history("s1", "u1") == []


# ---------- _prepare_session ----------


class _FakeGraph:
    """假图：aget_state 返回一个含指定 messages 的状态快照。"""

    def __init__(self, messages):
        self._messages = messages

    async def aget_state(self, config):
        return SimpleNamespace(values={"messages": self._messages})


async def test_prepare_session_seeds_when_no_checkpoint(monkeypatch):
    # 无 checkpoint（全新 / 迁移前旧会话）：应从 PG 灌历史作为 seed
    monkeypatch.setattr(
        chat_service, "_load_history", lambda sid, uid: [HumanMessage(content="旧消息")]
    )
    saved = []
    monkeypatch.setattr(
        chat_service.pg_client, "save_message", lambda *a, **k: saved.append(a)
    )

    graph = _FakeGraph(messages=[])
    seed = await chat_service._prepare_session(graph, {}, "s1", "u1", "新问题")

    assert [m.content for m in seed] == ["旧消息"]
    # 本轮用户消息已落库
    assert saved and saved[0][1] == "user" and saved[0][2] == "新问题"


async def test_prepare_session_skips_seed_when_checkpoint_exists(monkeypatch):
    # 已有 checkpoint：不应重复灌历史（否则与恢复状态重复）
    monkeypatch.setattr(
        chat_service, "_load_history", lambda sid, uid: [HumanMessage(content="不该被用")]
    )
    monkeypatch.setattr(chat_service.pg_client, "save_message", lambda *a, **k: None)

    graph = _FakeGraph(messages=[HumanMessage(content="已有状态")])
    seed = await chat_service._prepare_session(graph, {}, "s1", "u1", "新问题")

    assert seed == []


# ---------- 透传层 ----------


def test_history_delegates_to_pg(monkeypatch):
    rows = [{"id": 1, "role": "user", "content": "x"}]
    monkeypatch.setattr(
        chat_service.pg_client, "list_messages", lambda sid, uid, limit=None: rows
    )
    assert chat_service.history("s1", "u1", limit=10) == rows


async def test_delete_session_returns_count_and_clears_checkpoint(monkeypatch):
    monkeypatch.setattr(chat_service.pg_client, "delete_session", lambda sid, uid: 3)
    deleted_threads = []

    async def fake_adelete_thread(thread_id):
        deleted_threads.append(thread_id)

    monkeypatch.setattr(chat_service.checkpointer, "adelete_thread", fake_adelete_thread)

    result = await chat_service.delete_session("s1", "u1")

    assert result == {"session_id": "s1", "deleted_messages": 3}
    # checkpoint 按 user_id:session_id 拼接的 thread 一并清理
    assert deleted_threads == ["u1:s1"]


async def test_delete_session_survives_checkpoint_error(monkeypatch):
    # checkpoint 清理失败不应影响历史记录的删除结果
    monkeypatch.setattr(chat_service.pg_client, "delete_session", lambda sid, uid: 2)

    async def boom(thread_id):
        raise RuntimeError("pool closed")

    monkeypatch.setattr(chat_service.checkpointer, "adelete_thread", boom)

    result = await chat_service.delete_session("s1", "u1")
    assert result == {"session_id": "s1", "deleted_messages": 2}


def test_list_sessions_delegates_to_pg(monkeypatch):
    sessions = [{"session_id": "s1", "message_count": 2}]
    monkeypatch.setattr(
        chat_service.pg_client, "list_sessions", lambda uid, limit=None: sessions
    )
    assert chat_service.list_sessions("u1", limit=5) == sessions
