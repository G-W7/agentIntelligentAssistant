"""天气查询技能（自定义示例）：演示「放文件即注册」的最小可用自定义工作者。

把本文件放进 app/skills/ 并重启服务，registry.discover() 会自动导入并注册模块级
`skill` 实例，weather 随即成为一个新的路由目标与图节点——无需改动任何编排代码
（agent_graph.py / agents.py 均写死为零个具体技能）。

实现上调用免费的 Open-Meteo API（无需 API Key）：先用 LLM 结构化抽取城市，再经
地理编码拿到经纬度并查询实时天气，最后交由 LLM 组织成自然语言回答；任一环节失败
都会优雅降级为一句可读的说明，不影响其它技能与整体可用性。
"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.core.agents import last_human_text
from app.core.llm import get_chat_model
from app.skills.base import Skill, SkillMetadata

if TYPE_CHECKING:  # 仅类型检查期导入，避免与 app.core.agents 形成运行时导入环
    from app.core.agents import AgentState

logger = logging.getLogger(__name__)

_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_HTTP_TIMEOUT = 10  # 秒；示例用标准库 urllib，阻塞调用统一走 asyncio.to_thread

# WMO 天气代码 → 中文描述（对应 Open-Meteo current.weather_code）
_WEATHER_CODES: dict[int, str] = {
    0: "晴",
    1: "晴间多云",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "大毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "强冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "小阵雨",
    81: "阵雨",
    82: "强阵雨",
    85: "阵雪",
    86: "强阵雪",
    95: "雷暴",
    96: "雷暴伴冰雹",
    99: "强雷暴伴冰雹",
}

WEATHER_SYSTEM_PROMPT = """你是天气播报助手。请依据下面提供的实时天气数据，用简洁自然的中文回答用户的问题。
只依据给定数据作答，不要编造未提供的信息；数据不足以回答时如实说明。

实时天气数据（JSON）：
{data}"""


class WeatherLocation(BaseModel):
    """从用户问题中抽取的待查询城市（用结构化输出约束 LLM 只返回城市名）。"""

    city: str = Field(description="要查询天气的城市名，优先使用规范的中文或英文名")


def _http_get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    """标准库实现的 GET 请求并解析 JSON（阻塞，调用方用 asyncio.to_thread 包装）。"""
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{url}?{query}",
        headers={"User-Agent": "agent-intelligent-assistant/1.0"},
    )
    with urllib.request.urlopen(request, timeout=_HTTP_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def _geocode(city: str) -> dict[str, Any] | None:
    """把城市名解析为经纬度；无匹配时返回 None。"""
    data = _http_get_json(
        _GEOCODE_URL, {"name": city, "count": 1, "language": "zh", "format": "json"}
    )
    results = data.get("results") or []
    return results[0] if results else None


def _current_weather(latitude: float, longitude: float) -> dict[str, Any]:
    """查询给定坐标的当前天气（温度 / 湿度 / 天气代码 / 风速）。"""
    data = _http_get_json(
        _FORECAST_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "timezone": "auto",
        },
    )
    return data.get("current") or {}


class WeatherSkill(Skill):
    """天气工作者：查询指定城市的实时天气并生成自然语言播报。"""

    metadata = SkillMetadata(
        name="weather",
        label="天气查询",
        description=(
            "查询某个城市当前的实时天气（温度、天气状况、湿度、风速等）。"
            "当用户询问某地天气、今天冷不冷、要不要带伞等问题时选择此技能。"
        ),
        icon="cloud-sun",
        color="cyan",
        kind="custom",
    )

    async def _extract_city(self, question: str) -> str:
        """用结构化输出从用户问题里抽取城市名；失败则回退为原始问题文本。"""
        try:
            structured = get_chat_model().with_structured_output(
                WeatherLocation, method="function_calling"
            )
            location = await structured.ainvoke(
                [
                    SystemMessage(content="从用户问题中抽取要查询天气的城市名。"),
                    HumanMessage(content=question),
                ]
            )
            return (location.city or "").strip() or question
        except Exception:  # noqa: BLE001
            logger.warning("城市抽取失败，回退为原始问题文本", exc_info=True)
            return question

    async def run(self, state: "AgentState") -> dict[str, Any]:
        question = last_human_text(state["messages"])
        city = await self._extract_city(question)

        try:
            place = await asyncio.to_thread(_geocode, city)
        except Exception as exc:  # noqa: BLE001
            logger.exception("地理编码失败")
            return {
                "messages": [AIMessage(content=f"天气服务暂时不可用：{exc}")],
                "sources": [],
            }

        if not place:
            return {
                "messages": [
                    AIMessage(content=f"没有找到城市「{city}」，请确认地名后重试。")
                ],
                "sources": [],
            }

        try:
            current = await asyncio.to_thread(
                _current_weather, place["latitude"], place["longitude"]
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("天气数据查询失败")
            return {
                "messages": [AIMessage(content=f"天气数据获取失败：{exc}")],
                "sources": [],
            }

        raw_code = current.get("weather_code")
        code = int(raw_code) if raw_code is not None else -1
        summary = {
            "地点": place.get("name", city),
            "天气": _WEATHER_CODES.get(code, f"未知（代码 {code}）"),
            "气温℃": current.get("temperature_2m"),
            "相对湿度%": current.get("relative_humidity_2m"),
            "风速km/h": current.get("wind_speed_10m"),
        }

        prompt = WEATHER_SYSTEM_PROMPT.format(
            data=json.dumps(summary, ensure_ascii=False)
        )
        response = await get_chat_model().ainvoke(
            [SystemMessage(content=prompt), *state["messages"]]
        )
        sources = [
            {
                "kind": "tool",
                "index": 1,
                "tool_name": "open-meteo",
                "content": json.dumps(summary, ensure_ascii=False)[:300],
            }
        ]
        return {"messages": [response], "sources": sources}


skill = WeatherSkill()
