"""LangGraph Checkpointer 工厂与生命周期管理。

默认后端：把每个 thread（会话）的图状态（含 messages）持久化到 PostgreSQL，使多进程 /
多实例部署时同一会话落到任意实例都能恢复多轮上下文。

为什么用「同步 PostgresSaver + 线程池适配」而非 AsyncPostgresSaver：
- psycopg 3 的异步驱动依赖 SelectorEventLoop，而 uvicorn 在 Windows 上默认用
  ProactorEventLoop（且通过 loop_factory 显式指定，无法用 policy 覆盖），
  AsyncPostgresSaver 会直接连不上库；
- 本项目已统一采用「同步 DB 调用 + asyncio.to_thread」约定（见 pg_client），
  这里沿用同一约定包装同步 PostgresSaver，使其与事件循环类型无关，也无需改变
  uvicorn 启动方式。

无法初始化（缺依赖 / 连不上库 / 显式配置 memory 后端）时回退进程内 MemorySaver，
保证单实例开发与测试仍可运行（代价是重启丢失、无法多实例共享）。

连接池说明：checkpointer 使用独立的 psycopg 3 连接池，与 pg_client 的 psycopg2
连接池并存——langgraph-checkpoint-postgres 仅支持 psycopg 3。
"""

import asyncio
import logging
from typing import Any, AsyncIterator

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

from app.config import get_settings

logger = logging.getLogger(__name__)

# 进程级 Checkpointer 单例。由 get_checkpointer() 首次构造并缓存，
# init_checkpointer() 负责打开连接池并建表。
_checkpointer: Any = None


class ThreadedPostgresSaver(BaseCheckpointSaver):
    """用 asyncio.to_thread 把同步 PostgresSaver 的阻塞调用适配为 LangGraph 异步接口。

    同步实现运行在线程池里，不占用事件循环，因此不受 Windows ProactorEventLoop 限制。
    """

    def __init__(self, sync_saver: Any) -> None:
        super().__init__(serde=sync_saver.serde)
        self._saver = sync_saver

    # ---- 生命周期辅助（在 lifespan 内经 to_thread 调用）----

    def _open_and_setup(self) -> None:
        """打开连接池并建表（阻塞调用，需在 to_thread 中执行）。幂等。"""
        self._saver.conn.open(wait=True)
        self._saver.setup()

    def _close(self) -> None:
        """关闭连接池（阻塞调用，需在 to_thread 中执行）。"""
        self._saver.conn.close()

    # ---- 同步接口：直接透传 ----

    def get_tuple(self, config):  # noqa: D102
        return self._saver.get_tuple(config)

    def list(self, config, *, filter=None, before=None, limit=None):  # noqa: D102
        return self._saver.list(config, filter=filter, before=before, limit=limit)

    def put(self, config, checkpoint, metadata, new_versions):  # noqa: D102
        return self._saver.put(config, checkpoint, metadata, new_versions)

    def put_writes(self, config, writes, task_id, task_path=""):  # noqa: D102
        return self._saver.put_writes(config, writes, task_id, task_path)

    def delete_thread(self, thread_id):  # noqa: D102
        return self._saver.delete_thread(thread_id)

    # ---- 异步接口：丢到线程池执行同步实现，避免阻塞事件循环 ----

    async def aget_tuple(self, config):  # noqa: D102
        return await asyncio.to_thread(self._saver.get_tuple, config)

    async def alist(  # noqa: D102
        self, config, *, filter=None, before=None, limit=None
    ) -> AsyncIterator[Any]:
        # list() 是生成器：在线程内整体物化后逐项产出，避免跨线程持有游标
        items = await asyncio.to_thread(
            lambda: list(
                self._saver.list(config, filter=filter, before=before, limit=limit)
            )
        )
        for item in items:
            yield item

    async def aput(self, config, checkpoint, metadata, new_versions):  # noqa: D102
        return await asyncio.to_thread(
            self._saver.put, config, checkpoint, metadata, new_versions
        )

    async def aput_writes(self, config, writes, task_id, task_path=""):  # noqa: D102
        return await asyncio.to_thread(
            self._saver.put_writes, config, writes, task_id, task_path
        )

    async def adelete_thread(self, thread_id):  # noqa: D102
        return await asyncio.to_thread(self._saver.delete_thread, thread_id)


def _build_postgres_saver() -> ThreadedPostgresSaver:
    """构造基于同步连接池的 ThreadedPostgresSaver（池 open=False，延迟到启动阶段打开）。"""
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg_pool import ConnectionPool

    settings = get_settings()
    pool = ConnectionPool(
        conninfo=settings.postgres_dsn,
        min_size=1,
        max_size=settings.postgres_pool_size,
        open=False,
        check=ConnectionPool.check_connection,
        # autocommit + prepare_threshold=0 是 langgraph postgres saver 的推荐配置：
        # 兼容 pgbouncer 等连接代理，避免预编译语句在连接复用时出错。
        kwargs={"autocommit": True, "prepare_threshold": 0},
    )
    return ThreadedPostgresSaver(PostgresSaver(pool))


def get_checkpointer() -> Any:
    """返回进程级 Checkpointer 单例，供图编译（get_graph）使用。

    构造不触发 DB 连接（连接池 open=False），因此可在任意上下文安全调用；
    连接池在 init_checkpointer() 中打开。依赖缺失时回退 MemorySaver。
    """
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    if get_settings().checkpoint_backend == "memory":
        logger.info("Checkpointer 后端：MemorySaver（进程内，仅单实例，重启丢失）")
        _checkpointer = MemorySaver()
        return _checkpointer

    try:
        _checkpointer = _build_postgres_saver()
        logger.info("Checkpointer 后端：PostgresSaver（PostgreSQL 持久化，支持多实例）")
    except Exception:
        logger.warning("PostgresSaver 构造失败，回退 MemorySaver", exc_info=True)
        _checkpointer = MemorySaver()
    return _checkpointer


async def init_checkpointer() -> None:
    """打开连接池并建表（幂等），由应用 lifespan 启动阶段调用。

    必须在任何 get_graph() 调用之前完成，以便图编译时拿到已就绪的共享单例；
    PostgreSQL 不可用时回退 MemorySaver，让服务降级运行而非启动失败。
    """
    global _checkpointer
    saver = get_checkpointer()
    if not isinstance(saver, ThreadedPostgresSaver):
        return
    try:
        await asyncio.to_thread(saver._open_and_setup)
        logger.info("PostgresSaver 就绪，checkpoint 表结构已同步")
    except Exception:
        logger.warning("PostgresSaver 初始化失败，回退 MemorySaver", exc_info=True)
        _checkpointer = MemorySaver()


async def close_checkpointer() -> None:
    """关闭连接池并释放资源，应用关闭时由 lifespan 调用。"""
    global _checkpointer
    if isinstance(_checkpointer, ThreadedPostgresSaver):
        try:
            await asyncio.to_thread(_checkpointer._close)
        except Exception:
            logger.warning("关闭 Checkpointer 连接池时出错", exc_info=True)
    _checkpointer = None


async def adelete_thread(thread_id: str) -> None:
    """删除指定 thread 的全部 checkpoint 状态。

    会话被删除时调用：PostgresSaver 会把上下文持久化在 DB，仅删 chat_history 不足以
    清除记忆，多实例部署下已删会话的上下文会从 checkpoint「复活」，故需一并清理。
    MemorySaver 同样实现该方法；对不支持的实现则静默跳过。
    """
    deleter = getattr(get_checkpointer(), "adelete_thread", None)
    if deleter is not None:
        await deleter(thread_id)
