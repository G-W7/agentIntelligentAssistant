"""app/models/schemas.py 的单元测试：请求/响应模型的字段校验边界。"""

import pytest
from pydantic import ValidationError

from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    RegisterRequest,
    SourceItem,
)


# ---------- RegisterRequest：用户名 pattern 与密码长度 ----------


@pytest.mark.parametrize(
    "username",
    ["alice", "bob_1", "user.name", "a@b.com", "a+b-c", "中文用户", "用户123"],
)
def test_register_accepts_valid_usernames(username):
    req = RegisterRequest(username=username, password="secret123")
    assert req.username == username


@pytest.mark.parametrize(
    "username",
    ["a", "has space", "bad!char", "bad#tag", "x" * 51],
)
def test_register_rejects_invalid_usernames(username):
    with pytest.raises(ValidationError):
        RegisterRequest(username=username, password="secret123")


@pytest.mark.parametrize("password", ["12345", "x" * 129])
def test_register_rejects_bad_password_length(password):
    with pytest.raises(ValidationError):
        RegisterRequest(username="alice", password=password)


def test_register_accepts_boundary_password():
    # 6 位为下边界，应通过
    assert RegisterRequest(username="alice", password="123456").password == "123456"


# ---------- ChatRequest ----------


def test_chat_request_default_session_id():
    req = ChatRequest(message="你好")
    assert req.session_id == "default"


def test_chat_request_rejects_empty_message():
    with pytest.raises(ValidationError):
        ChatRequest(message="")


def test_chat_request_rejects_too_long_message():
    with pytest.raises(ValidationError):
        ChatRequest(message="x" * 8001)


# ---------- ChatResponse / SourceItem / 字面量约束 ----------


def test_chat_response_defaults():
    resp = ChatResponse(session_id="s1", route="chat", answer="hi")
    assert resp.route_reason == ""
    assert resp.sources == []


def test_chat_response_rejects_invalid_route():
    with pytest.raises(ValidationError):
        ChatResponse(session_id="s1", route="unknown", answer="hi")


def test_source_item_rejects_invalid_kind():
    with pytest.raises(ValidationError):
        SourceItem(kind="other")


def test_source_item_defaults():
    item = SourceItem(kind="web")
    assert item.score == 0.0
    assert item.content == ""
    assert item.title is None


# ---------- HealthResponse ----------


def test_health_response_requires_status_literal():
    health = HealthResponse(status="ok", postgres=True, milvus=True)
    assert health.milvus_vectors == 0
    with pytest.raises(ValidationError):
        HealthResponse(status="bad", postgres=True, milvus=True)
