"""app/db/checkpointer.py 的单元测试。

只覆盖不触发真实 PostgreSQL 连接的分支：memory 后端、构造失败回退，
以及 adelete_thread 对 MemorySaver 的兼容性。每个测试前把进程级单例重置为 None。
"""

import pytest
from langgraph.checkpoint.memory import MemorySaver

from app.config import get_settings
from app.db import checkpointer


@pytest.fixture(autouse=True)
def _reset_singleton():
    """每个测试前后清空进程级 Checkpointer 单例，避免相互污染。"""
    checkpointer._checkpointer = None
    yield
    checkpointer._checkpointer = None


def _force_backend(monkeypatch, backend: str):
    """把 checkpointer.get_settings 固定为指定 checkpoint_backend 的配置。"""
    settings = get_settings()
    monkeypatch.setattr(
        checkpointer, "get_settings", lambda: type(settings)(
            _env_file=None, checkpoint_backend=backend
        )
    )


def test_get_checkpointer_memory_backend(monkeypatch):
    _force_backend(monkeypatch, "memory")
    saver = checkpointer.get_checkpointer()
    assert isinstance(saver, MemorySaver)


def test_get_checkpointer_caches_singleton(monkeypatch):
    _force_backend(monkeypatch, "memory")
    assert checkpointer.get_checkpointer() is checkpointer.get_checkpointer()


def test_get_checkpointer_falls_back_on_build_error(monkeypatch):
    # postgres 后端但底层构造抛错（如缺依赖）：应回退 MemorySaver 而非崩溃
    _force_backend(monkeypatch, "postgres")

    def boom():
        raise RuntimeError("psycopg3 not available")

    monkeypatch.setattr(checkpointer, "_build_postgres_saver", boom)
    assert isinstance(checkpointer.get_checkpointer(), MemorySaver)


async def test_init_checkpointer_memory_backend(monkeypatch):
    _force_backend(monkeypatch, "memory")
    await checkpointer.init_checkpointer()
    assert isinstance(checkpointer._checkpointer, MemorySaver)


async def test_adelete_thread_memory_no_error(monkeypatch):
    # MemorySaver 实现了 adelete_thread，删除不存在的 thread 也不应抛异常
    monkeypatch.setattr(checkpointer, "_checkpointer", MemorySaver())
    await checkpointer.adelete_thread("u1:s1")


async def test_close_checkpointer_memory_resets_singleton(monkeypatch):
    monkeypatch.setattr(checkpointer, "_checkpointer", MemorySaver())
    await checkpointer.close_checkpointer()
    assert checkpointer._checkpointer is None
