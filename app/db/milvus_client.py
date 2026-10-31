"""Milvus 向量库访问层。

Collection schema 对应设计文档 4.4：pk / vector / content / source_file_id，
HNSW 索引 + COSINE 度量，enable_dynamic_field 用于附带 page 等切片元数据。
"""

import logging
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

_client: Any = None


def get_client() -> Any:
    """惰性创建 MilvusClient，导入本模块不会触发网络连接。"""
    global _client
    if _client is None:
        from pymilvus import MilvusClient

        _client = MilvusClient(uri=get_settings().milvus_uri)
    return _client


def close_client() -> None:
    """关闭 MilvusClient 连接，应用关闭时由 lifespan 调用。"""
    global _client
    if _client is not None:
        try:
            _client.close()
        except Exception:
            logger.warning("Milvus 连接关闭异常", exc_info=True)
        _client = None


def init_collection() -> bool:
    """collection 不存在时按文档 schema 创建。已存在则跳过。"""
    from pymilvus import DataType

    settings = get_settings()
    client = get_client()
    name = settings.milvus_collection

    if client.has_collection(name):
        logger.info("Milvus collection %s 已存在", name)
        return True

    schema = client.create_schema(auto_id=False, enable_dynamic_field=True)
    schema.add_field("pk", DataType.VARCHAR, is_primary=True, max_length=128)
    schema.add_field(
        "vector", DataType.FLOAT_VECTOR, dim=settings.embedding_dimensions
    )
    schema.add_field("content", DataType.VARCHAR, max_length=65535)
    schema.add_field("source_file_id", DataType.VARCHAR, max_length=64)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="vector",
        index_type="HNSW",
        metric_type="COSINE",
        params={"M": 16, "efConstruction": 200},
    )

    client.create_collection(name, schema=schema, index_params=index_params)
    logger.info(
        "已创建 Milvus collection %s（dim=%d, HNSW/COSINE）",
        name,
        settings.embedding_dimensions,
    )
    return True


def _quote(value: str) -> str:
    """转义布尔表达式中的字符串字面量，防止表达式注入。"""
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_file_filter(file_ids: list[str]) -> str:
    """把文件 ID 列表拼成 Milvus 过滤表达式 source_file_id in [...]；空列表返回空串表示不过滤。"""
    if not file_ids:
        return ""
    joined = ", ".join(_quote(fid) for fid in file_ids)
    return f"source_file_id in [{joined}]"


def insert_chunks(rows: list[dict[str, Any]]) -> int:
    """批量插入切片向量行，返回插入条数；空列表直接返回 0，不触发网络请求。"""
    if not rows:
        return 0
    get_client().insert(collection_name=get_settings().milvus_collection, data=rows)
    return len(rows)


def search(
    query_vector: list[float], top_k: int | None = None, file_ids: list[str] | None = None
) -> list[dict[str, Any]]:
    """向量检索，返回 [{content, source_file_id, page, score}]，score 越大越相关。"""
    settings = get_settings()
    expr = build_file_filter(file_ids or [])

    raw = get_client().search(
        collection_name=settings.milvus_collection,
        data=[query_vector],
        limit=top_k or settings.milvus_top_k,
        filter=expr,
        output_fields=["content", "source_file_id", "page"],
        search_params={"metric_type": "COSINE", "params": {"ef": 64}},
    )

    hits: list[dict[str, Any]] = []
    for item in raw[0] if raw else []:
        entity = item.get("entity", {})
        hits.append(
            {
                "content": entity.get("content", ""),
                "source_file_id": entity.get("source_file_id", ""),
                "page": entity.get("page"),
                "score": float(item.get("distance", 0.0)),
            }
        )
    return hits


def delete_by_file(file_id: str) -> int:
    """删除某文件的全部切片向量，返回删除条数。"""
    result = get_client().delete(
        collection_name=get_settings().milvus_collection,
        filter=f"source_file_id == {_quote(file_id)}",
    )
    return int(result.get("delete_count", 0)) if isinstance(result, dict) else 0


def collection_stats() -> dict[str, Any]:
    """返回 collection 是否存在及向量行数，供 /api/health 健康检查使用。"""
    client = get_client()
    name = get_settings().milvus_collection
    if not client.has_collection(name):
        return {"exists": False, "row_count": 0}
    stats = client.get_collection_stats(name)
    return {"exists": True, "row_count": int(stats.get("row_count", 0))}
