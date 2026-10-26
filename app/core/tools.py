"""外部工具封装：Tavily 联网搜索（设计文档 4.1 搜索 Agent 的工具）。

直接使用 tavily-python 而非 langchain-community 的 TavilySearchResults，
避免绑定 LangChain 集成包频繁变动的导入路径。
"""

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class WebResult:
    """单条联网搜索结果：标题、URL、正文摘要与相关性分数。"""

    title: str
    url: str
    content: str
    score: float = 0.0


@dataclass
class SearchOutcome:
    """一次搜索的整体产出：结果列表 + Tavily 官方生成的摘要答案。"""

    results: list[WebResult] = field(default_factory=list)
    answer: str = ""


@lru_cache
def _tavily_client() -> Any:
    """惰性创建并缓存 Tavily 客户端；未配置 API Key 时抛 RuntimeError。"""
    from tavily import TavilyClient

    api_key = get_settings().tavily_api_key
    if not api_key:
        raise RuntimeError("未配置 TAVILY_API_KEY，联网搜索不可用")
    return TavilyClient(api_key=api_key)


def web_search(query: str, max_results: int | None = None) -> SearchOutcome:
    """执行联网搜索：调用 Tavily API 并把原始返回解析为结构化结果。

    max_results 缺省时使用配置的 tavily_max_results。
    """
    settings = get_settings()
    raw = _tavily_client().search(
        query=query,
        max_results=max_results or settings.tavily_max_results,
        search_depth="basic",
        include_answer=True,
    )

    results = [
        WebResult(
            title=item.get("title", ""),
            url=item.get("url", ""),
            content=item.get("content", ""),
            score=float(item.get("score", 0.0)),
        )
        for item in raw.get("results", [])
    ]
    logger.info("Tavily 检索 %r 返回 %d 条结果", query, len(results))
    return SearchOutcome(results=results, answer=raw.get("answer", "") or "")


def format_web_context(outcome: SearchOutcome) -> str:
    """把搜索结果格式化为带 [N] 编号的文本块，供 search_worker 拼入 Prompt。"""
    blocks = []
    if outcome.answer:
        blocks.append(f"[搜索摘要]\n{outcome.answer}")
    for index, item in enumerate(outcome.results, start=1):
        blocks.append(f"[{index}] {item.title}\n{item.url}\n{item.content}")
    return "\n\n".join(blocks)
