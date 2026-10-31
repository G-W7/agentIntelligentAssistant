"""Langfuse 可观测性接入（可选）。

仅当 langfuse_enabled=true、密钥齐全且已安装 langfuse 包时才真正启用；
任何一环缺失都退化为 no-op，保证应用照常启动与运行。
"""

import logging
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

_client: Any = None
_enabled: bool = False


def init_langfuse() -> None:
    """在应用启动时构造 Langfuse 单例客户端并做鉴权自检。"""
    global _client, _enabled
    settings = get_settings()

    if not (
        settings.langfuse_enabled
        and settings.langfuse_public_key
        and settings.langfuse_secret_key
    ):
        logger.info("Langfuse 未启用（开关关闭或密钥未配置）")
        return

    try:
        from langfuse import Langfuse
    except ImportError:
        logger.warning(
            "已开启 Langfuse 但未安装依赖，跳过。安装：uv sync --extra langfuse"
        )
        return

    try:
        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_base_url,
            sample_rate=settings.langfuse_sample_rate,
        )
        if _client.auth_check():
            _enabled = True
            logger.info("Langfuse 追踪已启用 → %s", settings.langfuse_base_url)
        else:
            logger.warning("Langfuse 鉴权失败，请检查 public/secret key 与 host")
            _client = None
    except Exception:
        logger.warning("Langfuse 初始化失败，追踪功能将被禁用", exc_info=True)
        _client = None


def is_enabled() -> bool:
    return _enabled


def build_callbacks() -> list[Any]:
    """返回传给 LangGraph 的 callbacks 列表；未启用时返回空列表。

    v3 的 CallbackHandler 无需构造参数，会自动使用已初始化的单例客户端；
    user_id / session_id / tags 等属性通过 invoke 的 metadata 传入。
    """
    if not _enabled:
        return []
    try:
        from langfuse.langchain import CallbackHandler

        return [CallbackHandler()]
    except Exception:
        logger.warning("创建 Langfuse CallbackHandler 失败", exc_info=True)
        return []


def shutdown_langfuse() -> None:
    """应用关闭时刷新队列并释放客户端，避免丢失未上报的 span。"""
    global _client, _enabled
    if _client is not None:
        try:
            _client.shutdown()
        except Exception:
            logger.warning("Langfuse 关闭异常", exc_info=True)
        _client = None
    _enabled = False