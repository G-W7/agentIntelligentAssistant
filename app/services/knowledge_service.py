"""知识库业务逻辑：上传落盘、元数据入库、向量化状态流转、级联删除。

磁盘文件名统一使用 file_id，不采用用户提交的原始文件名，
既避免重名覆盖，也杜绝路径穿越风险。
"""

import logging
from pathlib import Path
from typing import Any

from app.config import ALLOWED_EXTENSIONS, get_settings
from app.db import milvus_client, pg_client
from app.services import rag_service

logger = logging.getLogger(__name__)


def stored_path_for(file_id: str, file_type: str) -> Path:
    """磁盘路径的唯一构造点，file_type 为不含点的扩展名。"""
    return get_settings().upload_dir / f"{file_id}.{file_type}"


def _validate(original_filename: str, raw: bytes) -> str:
    """上传校验：扩展名白名单、内容非空、不超过大小上限。

    通过后返回不含点的扩展名，否则抛 ValueError（由路由层转 400）。
    """
    settings = get_settings()
    suffix = Path(original_filename or "").suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        allowed = "、".join(sorted(ALLOWED_EXTENSIONS))
        raise ValueError(f"不支持的文件类型 {suffix or '(无扩展名)'}，仅支持：{allowed}")

    if not raw:
        raise ValueError("上传内容为空")

    if len(raw) > settings.max_upload_bytes:
        raise ValueError(f"文件超过大小上限 {settings.max_upload_mb} MB")

    return suffix.lstrip(".")


def upload_and_ingest(original_filename: str, raw: bytes) -> dict[str, Any]:
    """保存文件并完成向量化，返回文件记录与切片数。

    向量化失败时记录状态置为 error 并抛出异常，文件与元数据保留以便排查。
    """
    file_type = _validate(original_filename, raw)
    settings = get_settings()

    record = pg_client.create_file_record(
        filename=Path(original_filename).name,
        file_type=file_type,
        file_size=len(raw),
    )
    file_id = record["id"]

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    stored_path = stored_path_for(file_id, file_type)
    stored_path.write_bytes(raw)

    try:
        chunk_count = rag_service.ingest_file(file_id, stored_path)
    except Exception:
        pg_client.set_file_status(file_id, "error")
        logger.exception("文件 %s 向量化失败", file_id)
        raise

    status = "ready" if chunk_count else "error"
    pg_client.set_file_status(file_id, status)

    return {"file": pg_client.get_file(file_id), "chunk_count": chunk_count}


def list_files() -> list[dict[str, Any]]:
    """返回知识库全部文件记录（上传时间倒序）。"""
    return pg_client.list_files()


def delete_file(file_id: str) -> dict[str, Any]:
    """删除向量、元数据与磁盘文件。文件不存在时抛 ValueError。"""
    record = pg_client.get_file(file_id)
    if record is None:
        raise ValueError(f"文件不存在：{file_id}")

    try:
        deleted_vectors = milvus_client.delete_by_file(file_id)
    except Exception:
        logger.exception("删除 %s 的向量失败，仍继续清理元数据", file_id)
        deleted_vectors = 0

    pg_client.delete_file_record(file_id)
    stored_path_for(file_id, record["file_type"]).unlink(missing_ok=True)

    return {"file_id": file_id, "deleted_vectors": deleted_vectors}
