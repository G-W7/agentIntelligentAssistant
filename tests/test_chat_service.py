"""app/services/chat_service.py 的单元测试。

只覆盖不触发真实 Agent 图 / PostgreSQL 的部分：
- _text_of：字符串与多模态分块两种 content 形态；
- _load_history：把数据库行还原为 LangChain 消息对象（mock pg_client）；
- history / delete_session / list_sessions：透传层（mock pg_client）。
"""

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


# ---------- 透传层 ----------


def test_history_delegates_to_pg(monkeypatch):
    rows = [{"id": 1, "role": "user", "content": "x"}]
    monkeypatch.setattr(
        chat_service.pg_client, "list_messages", lambda sid, uid, limit=None: rows
    )
    assert chat_service.history("s1", "u1", limit=10) == rows


def test_delete_session_returns_count(monkeypatch):
    monkeypatch.setattr(chat_service.pg_client, "delete_session", lambda sid, uid: 3)
    result = chat_service.delete_session("s1", "u1")
    assert result == {"session_id": "s1", "deleted_messages": 3}


def test_list_sessions_delegates_to_pg(monkeypatch):
    sessions = [{"session_id": "s1", "message_count": 2}]
    monkeypatch.setattr(
        chat_service.pg_client, "list_sessions", lambda uid, limit=None: sessions
    )
    assert chat_service.list_sessions("u1", limit=5) == sessions
