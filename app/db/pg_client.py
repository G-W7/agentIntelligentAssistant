"""PostgreSQL 连接池与数据访问层。

同步实现（psycopg2）。异步端点中调用时请用 asyncio.to_thread 包装，
避免阻塞事件循环。
"""

import logging
from contextlib import contextmanager
from typing import Any
from uuid import UUID

from psycopg2 import pool as pg_pool
from psycopg2.extras import Json, RealDictCursor

from app.config import get_settings

logger = logging.getLogger(__name__)

# 建表 SQL：users（用户）+ knowledge_base（文件元数据）+ chat_history（对话历史）与索引。
# user_id 列用 ALTER TABLE ... ADD COLUMN IF NOT EXISTS 追加，兼容已存在的旧表结构。
_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_base (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(20),
    file_size BIGINT,
    upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'processing'
);

CREATE TABLE IF NOT EXISTS chat_history (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS user_id UUID;
ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS user_id UUID;

CREATE INDEX IF NOT EXISTS idx_chat_history_session
    ON chat_history (session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_history_user
    ON chat_history (user_id, session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_knowledge_base_user
    ON knowledge_base (user_id, upload_time);
"""

_pool: pg_pool.ThreadedConnectionPool | None = None


def init_db() -> None:
    """建立连接池并执行建表。重复调用是安全的。"""
    global _pool
    settings = get_settings()
    if _pool is None:
        _pool = pg_pool.ThreadedConnectionPool(
            minconn=1, maxconn=settings.postgres_pool_size, dsn=settings.postgres_dsn
        )
    with connection() as conn, conn.cursor() as cur:
        cur.execute(_SCHEMA)
    logger.info("PostgreSQL 就绪，表结构已同步")


def close_db() -> None:
    """关闭连接池并释放全部连接，应用关闭时由 lifespan 调用。"""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


@contextmanager
def connection():
    """从池中借出连接的上下文管理器。

    正常退出自动 commit，异常自动 rollback，最终必定归还连接；
    连接池未初始化时抛 RuntimeError。
    """
    if _pool is None:
        raise RuntimeError("连接池未初始化，请先调用 init_db()")
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def _serialize_file(row: dict[str, Any]) -> dict[str, Any]:
    """把 UUID / datetime 转成 JSON 友好的类型。"""
    data = dict(row)
    for key in ("id", "user_id"):
        if isinstance(data.get(key), UUID):
            data[key] = str(data[key])
    return data


# ---------------- users ----------------


def create_user(username: str, password_hash: str) -> dict[str, Any] | None:
    """插入新用户，返回完整记录；用户名已存在（唯一约束冲突）返回 None。"""
    from psycopg2 import IntegrityError

    try:
        with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "INSERT INTO users (username, password_hash) "
                "VALUES (%s, %s) RETURNING *",
                (username, password_hash),
            )
            return _serialize_file(cur.fetchone())
    except IntegrityError:
        return None


def get_user_by_username(username: str) -> dict[str, Any] | None:
    """按用户名查询用户（含 password_hash，仅供登录校验），不存在返回 None。"""
    with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        row = cur.fetchone()
        return _serialize_file(row) if row else None


def get_user_by_id(user_id: str) -> dict[str, Any] | None:
    """按 ID 查询用户，不存在返回 None。"""
    with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        return _serialize_file(row) if row else None


# ---------------- knowledge_base ----------------


def create_file_record(
    filename: str, file_type: str, file_size: int, user_id: str
) -> dict[str, Any]:
    """在 knowledge_base 表插入一条状态为 processing 的文件记录，归属指定用户。"""
    with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "INSERT INTO knowledge_base (filename, file_type, file_size, status, user_id) "
            "VALUES (%s, %s, %s, 'processing', %s) RETURNING *",
            (filename, file_type, file_size, user_id),
        )
        return _serialize_file(cur.fetchone())


def set_file_status(file_id: str, status: str) -> None:
    """更新文件的处理状态（ready / error 等）。"""
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE knowledge_base SET status = %s WHERE id = %s",
            (status, file_id),
        )


def get_file(file_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    """按 ID 查询单个文件记录，不存在返回 None。

    传入 user_id 时附加归属校验，防止跨用户访问他人文件。
    """
    with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        if user_id is None:
            cur.execute("SELECT * FROM knowledge_base WHERE id = %s", (file_id,))
        else:
            cur.execute(
                "SELECT * FROM knowledge_base WHERE id = %s AND user_id = %s",
                (file_id, user_id),
            )
        row = cur.fetchone()
        return _serialize_file(row) if row else None


def list_files(user_id: str) -> list[dict[str, Any]]:
    """按上传时间倒序返回指定用户的全部文件记录。"""
    with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM knowledge_base WHERE user_id = %s ORDER BY upload_time DESC",
            (user_id,),
        )
        return [_serialize_file(r) for r in cur.fetchall()]


def delete_file_record(file_id: str, user_id: str) -> bool:
    """删除指定用户的文件元数据记录，返回是否确实删除了行。"""
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM knowledge_base WHERE id = %s AND user_id = %s",
            (file_id, user_id),
        )
        return cur.rowcount > 0


def count_files() -> int:
    """返回知识库文件总数（全局），仅供 /api/health 健康检查统计使用。"""
    with connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM knowledge_base")
        return int(cur.fetchone()[0])


# ---------------- chat_history ----------------


def save_message(
    session_id: str,
    role: str,
    content: str,
    user_id: str,
    meta: dict[str, Any] | None = None,
) -> None:
    """向 chat_history 写入一条归属指定用户的消息；meta 以 JSONB 存储路由结果与引用来源等元数据。"""
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO chat_history (session_id, role, content, metadata, user_id) "
            "VALUES (%s, %s, %s, %s, %s)",
            (session_id, role, content, Json(meta) if meta is not None else None, user_id),
        )


def list_messages(session_id: str, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """按时间正序返回指定用户某会话最近 limit 条消息。"""
    with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM ("
            "  SELECT id, role, content, metadata, created_at FROM chat_history"
            "  WHERE session_id = %s AND user_id = %s ORDER BY created_at DESC, id DESC LIMIT %s"
            ") t ORDER BY created_at ASC, id ASC",
            (session_id, user_id, limit),
        )
        return cur.fetchall()


def delete_session(session_id: str, user_id: str) -> int:
    """删除指定用户某会话的全部消息，返回实际删除的行数。"""
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM chat_history WHERE session_id = %s AND user_id = %s",
            (session_id, user_id),
        )
        return cur.rowcount


def list_sessions(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """按最近活跃时间倒序返回指定用户的会话列表：ID、最后消息时间、消息数与预览。"""
    with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT session_id, MAX(created_at) AS last_message_at, COUNT(*) AS message_count,"
            "       (array_agg(content ORDER BY created_at DESC, id DESC))[1] AS preview"
            " FROM chat_history"
            " WHERE user_id = %s"
            " GROUP BY session_id"
            " ORDER BY last_message_at DESC"
            " LIMIT %s",
            (user_id, limit),
        )
        return cur.fetchall()
