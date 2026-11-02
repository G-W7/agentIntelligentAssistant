"""API 集成测试：用 FastAPI TestClient 打通"路由 → 依赖鉴权 → 响应模型"链路。

外部依赖（PostgreSQL / Milvus / Agent 图 / 联网）全部用 monkeypatch 替换，
只验证 HTTP 层的状态码、鉴权分支与响应体结构，不触网、不连库。

关键点：TestClient 不进入 with 上下文，因此不会触发 app.main 的 lifespan
（避免启动时真的去连 PG/Milvus）。
"""

import pytest
from fastapi.testclient import TestClient

from app.core import security
from app.db import milvus_client, pg_client
from app.main import app
from app.services import chat_service, knowledge_service

# 一个固定的假用户行；password_hash 由各测试按需替换为真实 bcrypt 串
USER = {"id": "u-1", "username": "alice", "password_hash": "x", "created_at": None}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _fixed_jwt_settings(monkeypatch, make_settings):
    """把 security.get_settings 固定为已知长密钥，使签发/校验不依赖真实 .env，
    同时避免短密钥触发 PyJWT 的 InsecureKeyLengthWarning。"""
    settings = make_settings(
        jwt_secret_key="api-integration-test-secret-key-0123456789abcdef",
        jwt_algorithm="HS256",
        access_token_expire_minutes=60,
    )
    monkeypatch.setattr(security, "get_settings", lambda: settings)


@pytest.fixture
def auth_headers(monkeypatch):
    """签发一个真实 JWT，并让鉴权依赖能回查到假用户，模拟已登录状态。"""
    monkeypatch.setattr(
        pg_client, "get_user_by_id", lambda uid: USER if uid == USER["id"] else None
    )
    token = security.create_access_token(USER["id"], USER["username"])
    return {"Authorization": f"Bearer {token}"}


# ============ 认证：注册 ============


def test_register_success(client, monkeypatch):
    monkeypatch.setattr(pg_client, "create_user", lambda username, pw_hash: dict(USER))
    resp = client.post(
        "/api/auth/register", json={"username": "alice", "password": "secret123"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["username"] == "alice"
    # 响应体不应泄露密码哈希
    assert "password_hash" not in body["user"]


def test_register_conflict(client, monkeypatch):
    monkeypatch.setattr(pg_client, "create_user", lambda username, pw_hash: None)
    resp = client.post(
        "/api/auth/register", json={"username": "alice", "password": "secret123"}
    )
    assert resp.status_code == 409


def test_register_dependency_unavailable(client, monkeypatch):
    def boom(username, pw_hash):
        raise RuntimeError("PG down")

    monkeypatch.setattr(pg_client, "create_user", boom)
    resp = client.post(
        "/api/auth/register", json={"username": "alice", "password": "secret123"}
    )
    assert resp.status_code == 503


def test_register_validation_error(client):
    # 密码不足 6 位 → Pydantic 校验失败 422
    resp = client.post("/api/auth/register", json={"username": "alice", "password": "123"})
    assert resp.status_code == 422


# ============ 认证：登录 ============


def test_login_success(client, monkeypatch):
    stored = dict(USER, password_hash=security.hash_password("secret123"))
    monkeypatch.setattr(pg_client, "get_user_by_username", lambda name: stored)
    resp = client.post(
        "/api/auth/login", json={"username": "alice", "password": "secret123"}
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_login_wrong_password(client, monkeypatch):
    stored = dict(USER, password_hash=security.hash_password("right-password"))
    monkeypatch.setattr(pg_client, "get_user_by_username", lambda name: stored)
    resp = client.post(
        "/api/auth/login", json={"username": "alice", "password": "wrong-password"}
    )
    assert resp.status_code == 401


def test_login_unknown_user(client, monkeypatch):
    monkeypatch.setattr(pg_client, "get_user_by_username", lambda name: None)
    resp = client.post(
        "/api/auth/login", json={"username": "ghost", "password": "secret123"}
    )
    assert resp.status_code == 401


def test_login_dependency_unavailable(client, monkeypatch):
    def boom(name):
        raise RuntimeError("PG down")

    monkeypatch.setattr(pg_client, "get_user_by_username", boom)
    resp = client.post(
        "/api/auth/login", json={"username": "alice", "password": "secret123"}
    )
    assert resp.status_code == 503


# ============ 认证：/me 与鉴权分支 ============


def test_me_returns_current_user(client, auth_headers):
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"


def test_me_without_token_is_401(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_invalid_token_is_401(client):
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert resp.status_code == 401


def test_me_deleted_user_is_401(client, monkeypatch):
    # 令牌有效但用户已被删除：回查返回 None → 401
    monkeypatch.setattr(pg_client, "get_user_by_id", lambda uid: None)
    token = security.create_access_token(USER["id"], USER["username"])
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


# ============ 健康检查 ============


def test_health_ok(client, monkeypatch):
    monkeypatch.setattr(pg_client, "count_files", lambda: 3)
    monkeypatch.setattr(
        milvus_client, "collection_stats", lambda: {"exists": True, "row_count": 10}
    )
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["postgres"] is True
    assert body["milvus"] is True
    assert body["milvus_vectors"] == 10
    assert body["knowledge_files"] == 3


def test_health_degraded(client, monkeypatch):
    def boom():
        raise RuntimeError("PG down")

    monkeypatch.setattr(pg_client, "count_files", boom)
    monkeypatch.setattr(
        milvus_client, "collection_stats", lambda: {"exists": False, "row_count": 0}
    )
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["postgres"] is False
    assert body["milvus"] is False


# ============ 对话 ============


def test_chat_success(client, auth_headers, monkeypatch):
    async def fake_chat(session_id, user_id, message):
        return {
            "session_id": session_id,
            "route": "chat",
            "route_reason": "闲聊",
            "answer": f"echo:{message}",
            "sources": [],
        }

    monkeypatch.setattr(chat_service, "chat", fake_chat)
    resp = client.post("/api/chat", json={"message": "你好"}, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "echo:你好"
    assert body["route"] == "chat"
    assert body["session_id"] == "default"


def test_chat_dependency_unavailable_503(client, auth_headers, monkeypatch):
    async def boom(session_id, user_id, message):
        raise RuntimeError("依赖不可用")

    monkeypatch.setattr(chat_service, "chat", boom)
    resp = client.post("/api/chat", json={"message": "hi"}, headers=auth_headers)
    assert resp.status_code == 503


def test_chat_agent_error_502(client, auth_headers, monkeypatch):
    async def boom(session_id, user_id, message):
        raise ValueError("LLM 崩了")

    monkeypatch.setattr(chat_service, "chat", boom)
    resp = client.post("/api/chat", json={"message": "hi"}, headers=auth_headers)
    assert resp.status_code == 502


def test_chat_requires_auth(client):
    resp = client.post("/api/chat", json={"message": "hi"})
    assert resp.status_code == 401


def test_chat_stream_emits_sse_events(client, auth_headers, monkeypatch):
    async def fake_stream(session_id, user_id, message):
        yield {"type": "start", "session_id": session_id}
        yield {"type": "delta", "content": "你"}
        yield {"type": "delta", "content": "好"}
        yield {"type": "done", "session_id": session_id, "answer": "你好"}

    monkeypatch.setattr(chat_service, "chat_stream", fake_stream)
    resp = client.post(
        "/api/chat/stream", json={"message": "hi"}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    text = resp.text
    assert "event: start" in text
    assert "event: delta" in text
    assert "event: done" in text


# ============ 历史 / 会话 ============


def test_get_history(client, auth_headers, monkeypatch):
    rows = [
        {"id": 1, "role": "user", "content": "hi", "created_at": "2026-01-01T00:00:00"},
        {"id": 2, "role": "assistant", "content": "hello", "created_at": "2026-01-01T00:00:01"},
    ]
    monkeypatch.setattr(chat_service, "history", lambda sid, uid, limit: rows)
    resp = client.get("/api/history?session_id=s1&limit=10", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert body[0]["role"] == "user"


def test_list_sessions(client, auth_headers, monkeypatch):
    rows = [
        {
            "session_id": "s1",
            "last_message_at": "2026-01-01T00:00:00",
            "message_count": 4,
            "preview": "hi",
        }
    ]
    monkeypatch.setattr(chat_service, "list_sessions", lambda uid, limit: rows)
    resp = client.get("/api/sessions", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()[0]["session_id"] == "s1"


def test_delete_session_ok(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        chat_service,
        "delete_session",
        lambda sid, uid: {"session_id": sid, "deleted_messages": 2},
    )
    resp = client.delete("/api/sessions/s1", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["deleted_messages"] == 2


def test_delete_session_not_found(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        chat_service,
        "delete_session",
        lambda sid, uid: {"session_id": sid, "deleted_messages": 0},
    )
    resp = client.delete("/api/sessions/empty", headers=auth_headers)
    assert resp.status_code == 404


# ============ 知识库文件 ============


def test_list_files(client, auth_headers, monkeypatch):
    rows = [
        {
            "id": "f1",
            "filename": "a.md",
            "file_type": "md",
            "file_size": 10,
            "status": "ready",
        }
    ]
    monkeypatch.setattr(knowledge_service, "list_files", lambda uid: rows)
    resp = client.get("/api/files", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()[0]["filename"] == "a.md"


def test_delete_file_not_found(client, auth_headers, monkeypatch):
    def boom(file_id, uid):
        raise ValueError("文件不存在")

    monkeypatch.setattr(knowledge_service, "delete_file", boom)
    # file_id 需为合法 UUID 才能通过路径参数校验
    resp = client.delete(
        "/api/files/00000000-0000-0000-0000-000000000000", headers=auth_headers
    )
    assert resp.status_code == 404


def test_delete_file_ok(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        knowledge_service,
        "delete_file",
        lambda file_id, uid: {"file_id": file_id, "deleted_vectors": 5},
    )
    resp = client.delete(
        "/api/files/11111111-1111-1111-1111-111111111111", headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["deleted_vectors"] == 5
