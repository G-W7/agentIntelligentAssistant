"""LLM 与 Embedding 模型工厂。

统一在此处构造模型实例，Agent 与 RAG 服务都从这里取，
避免配置散落各处。函数内部延迟导入，使应用在缺少可选依赖或
未配置密钥时仍能正常启动并暴露 /docs。
"""

from functools import lru_cache
from typing import Any

from app.config import get_settings


class DashScopeEmbeddings:
    """基于 DashScope（千问）原生 SDK 的 LangChain Embeddings 实现。

    支持自定义 base_http_api_url 网关；同步接口单批最多 25 条，
    内部按 batch_size 分批调用并拼接，保证顺序与输入一致。
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str | None = None,
        batch_size: int = 10,
    ) -> None:
        import dashscope

        self._dashscope = dashscope
        self.model = model
        self.batch_size = max(1, min(batch_size, 25))
        dashscope.api_key = api_key
        if base_url:
            dashscope.base_http_api_url = base_url

    def _embed(self, texts: list[str]) -> list[list[float]]:
        from http import HTTPStatus

        embeddings: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            resp = self._dashscope.TextEmbedding.call(
                model=self.model,
                input=batch,
            )
            if resp.status_code != HTTPStatus.OK:
                raise RuntimeError(
                    f"DashScope embedding 调用失败: "
                    f"code={resp.status_code}, message={getattr(resp, 'message', resp)}"
                )
            items = resp.output["embeddings"]
            # 官方 DashScope 用 text_index，部分第三方网关（如千问代理）用 index；
            # 有则按其排序保证与输入顺序一致，都没有则信任网关返回顺序。
            index_key = next(
                (k for k in ("text_index", "index") if items and k in items[0]),
                None,
            )
            if index_key:
                items = sorted(items, key=lambda x: x[index_key])
            embeddings.extend(self._extract_vector(it) for it in items)
        return embeddings

    @staticmethod
    def _extract_vector(item: dict) -> list[float]:
        """兼容不同网关的向量字段命名。"""
        for key in ("embedding", "vector"):
            if key in item:
                return item[key]
        raise KeyError(
            f"无法从返回项中解析向量，实际字段为: {list(item.keys())}"
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]


@lru_cache
def get_chat_model() -> Any:
    """构造并缓存 deepseek 对话模型单例。

    deepseek-flash 默认开启思考模式，思考模式下不支持 tool_choice=required
    与 json_schema 结构化输出（会返回 400）。这里默认关闭思考模式，
    以获得更低延迟并恢复 temperature 等采样参数的效果。
    """
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    return ChatOpenAI(
        model=settings.chat_model,
        temperature=settings.temperature,
        api_key=settings.deepseek_api_key or None,
        base_url=settings.deepseek_base_url or None,
        extra_body={"thinking": {"type": "disabled"}},
    )


@lru_cache
def get_embeddings() -> Any:
    """构造并缓存千问 DashScope Embedding 单例。

    维度须与 Milvus collection 一致（EMBEDDING_DIMENSIONS）。
    """
    settings = get_settings()

    if not settings.dashscope_api_key:
        raise RuntimeError("未配置 DASHSCOPE_API_KEY，无法初始化 Embedding 模型")

    return DashScopeEmbeddings(
        model=settings.embedding_model,
        api_key=settings.dashscope_api_key,
        base_url=settings.dashscope_base_url,
        batch_size=settings.dashscope_batch_size,
    )
