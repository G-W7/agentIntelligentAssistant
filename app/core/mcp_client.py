"""MCP 客户端：加载 mcp.json 配置并把外部 MCP server 的工具转为 LangChain 工具。

设计要点：
- 配置驱动：项目根 mcp.json 的 mcpServers 字段声明要连接的服务；
- 惰性 + 缓存：首次需要工具时才连接并缓存结果（进程内），失败降级为空列表；
- 容错：文件缺失 / 非法 JSON / 连接异常都只告警，不影响应用启动与其它技能。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

# 进程内工具缓存；None 表示尚未加载，[] 表示已加载但无可用工具
_tools_cache: list[Any] | None = None


def load_config() -> dict[str, Any]:
    """读取 mcp.json 的 mcpServers 配置。

    文件缺失、非法 JSON 或结构不符时返回空字典（视为未配置）。
    """
    path = get_settings().mcp_config_path
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("MCP 配置 %s 解析失败：%s", path, exc)
        return {}
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    return servers if isinstance(servers, dict) else {}


def list_servers() -> list[str]:
    """返回已配置的 MCP server 名称列表。"""
    return list(load_config().keys())


async def get_tools() -> list[Any]:
    """连接所有已配置的 MCP server 并返回可用工具列表；结果进程内缓存。

    未配置或连接失败时返回空列表（并缓存该结果，避免每次请求都重试）。
    """
    global _tools_cache
    if _tools_cache is not None:
        return _tools_cache

    config = load_config()
    if not config:
        _tools_cache = []
        return _tools_cache

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        client = MultiServerMCPClient(config)
        _tools_cache = await client.get_tools()
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP 工具加载失败：%s", exc)
        _tools_cache = []
    else:
        logger.info("已加载 %d 个 MCP 工具", len(_tools_cache))
    return _tools_cache


def reset_cache() -> None:
    """清空工具缓存（测试或配置变更后重新加载时使用）。"""
    global _tools_cache
    _tools_cache = None
