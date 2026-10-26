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

# 建表 SQL：knowledge_base（文件元数据）与 chat_history（对话历史）+ 会话索引
_SCHEMA = """
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

CREATE INDEX IF NOT EXISTS idx_chat_history_session
    ON chat_history (session_id, created_at);
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
    if isinstance(data.get("id"), UUID):
        data["id"] = str(data["id"])
    return data


# ---------------- knowledge_base ----------------


def create_file_record(filename: str, file_type: str, file_size: int) -> dict[str, Any]:
    """在 knowledge_base 表插入一条状态为 processing 的文件记录，返回完整记录。"""
    with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "INSERT INTO knowledge_base (filename, file_type, file_size, status) "
            "VALUES (%s, %s, %s, 'processing') RETURNING *",
            (filename, file_type, file_size),
        )
        return _serialize_file(cur.fetchone())


def set_file_status(file_id: str, status: str) -> None:
    """更新文件的处理状态（ready / error 等）。"""
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE knowledge_base SET status = %s WHERE id = %s",
            (status, file_id),
        )


def get_file(file_id: str) -> dict[str, Any] | None:
    """按 ID 查询单个文件记录，不存在返回 None。"""
    with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM knowledge_base WHERE id = %s", (file_id,))
        row = cur.fetchone()
        return _serialize_file(row) if row else None


def list_files() -> list[dict[str, Any]]:
    """按上传时间倒序返回全部文件记录。"""
    with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM knowledge_base ORDER BY upload_time DESC")
        return [_serialize_file(r) for r in cur.fetchall()]


def delete_file_record(file_id: str) -> bool:
    """删除文件元数据记录，返回是否确实删除了行。"""
    with connection() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM knowledge_base WHERE id = %s", (file_id,))
        return cur.rowcount > 0


# ---------------- chat_history ----------------


def save_message(
    session_id: str, role: str, content: str, meta: dict[str, Any] | None = None
) -> None:
    """向 chat_history 写入一条消息；meta 以 JSONB 存储路由结果与引用来源等元数据。"""
    with connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO chat_history (session_id, role, content, metadata) "
            "VALUES (%s, %s, %s, %s)",
            (session_id, role, content, Json(meta) if meta is not None else None),
        )


def list_messages(session_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """按时间正序返回最近 limit 条消息。"""
    with connection() as conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM ("
            "  SELECT id, role, content, metadata, created_at FROM chat_history"
            "  WHERE session_id = %s ORDER BY created_at DESC, id DESC LIMIT %s"
            ") t ORDER BY created_at ASC, id ASC",
            (session_id, limit),
        )
        return cur.fetchall()
