"""app/services/knowledge_service.py 的单元测试。

覆盖上传校验（扩展名白名单 / 空内容 / 超限）、磁盘路径构造、
上传入库的状态流转（ready / error）、级联删除与列表透传。
文件系统用 tmp_path，PostgreSQL / Milvus / RAG 全部 monkeypatch，不落真实副作用。
"""

import pytest

from app.services import knowledge_service
from app.services.knowledge_service import (
    _validate,
    delete_file,
    list_files,
    stored_path_for,
    upload_and_ingest,
)


@pytest.fixture
def svc_settings(monkeypatch, make_settings, tmp_path):
    """把 knowledge_service.get_settings 固定为：上传目录指向 tmp_path、上限 1 MB。"""
    settings = make_settings(max_upload_mb=1, upload_dir=tmp_path)
    monkeypatch.setattr(knowledge_service, "get_settings", lambda: settings)
    return settings


# ============ _validate：扩展名白名单 ============


@pytest.mark.parametrize(
    "filename,expected_type",
    [
        ("doc.pdf", "pdf"),
        ("note.md", "md"),
        ("note.MARKDOWN", "markdown"),  # 大写应被归一化
        ("readme.txt", "txt"),
        ("a.docx", "docx"),
        ("b.pptx", "pptx"),
        ("c.xlsx", "xlsx"),
        ("img.PNG", "png"),
        ("photo.jpeg", "jpeg"),
    ],
)
def test_validate_accepts_whitelisted(svc_settings, filename, expected_type):
    assert _validate(filename, b"some bytes") == expected_type


@pytest.mark.parametrize("filename", ["script.exe", "archive.zip", "data.csv", "noext"])
def test_validate_rejects_non_whitelisted(svc_settings, filename):
    with pytest.raises(ValueError, match="不支持的文件类型"):
        _validate(filename, b"some bytes")


def test_validate_rejects_empty_content(svc_settings):
    with pytest.raises(ValueError, match="内容为空"):
        _validate("doc.pdf", b"")


def test_validate_rejects_oversize(svc_settings):
    # 上限 1 MB，超出 1 字节即拒绝
    too_big = b"x" * (1024 * 1024 + 1)
    with pytest.raises(ValueError, match="超过大小上限"):
        _validate("doc.pdf", too_big)


def test_validate_accepts_boundary_size(svc_settings):
    # 恰好等于上限应通过
    exact = b"x" * (1024 * 1024)
    assert _validate("doc.pdf", exact) == "pdf"


# ============ stored_path_for ============


def test_stored_path_for_uses_file_id_and_type(svc_settings, tmp_path):
    path = stored_path_for("fid-123", "md")
    assert path == tmp_path / "fid-123.md"


# ============ upload_and_ingest ============


def _mock_pg_for_upload(monkeypatch, file_id="fid-1", file_type="md"):
    """把上传链路上的 pg_client 调用替换为可控假实现，返回状态记录器。"""
    calls = {"status": [], "created": []}

    def create_file_record(**kwargs):
        calls["created"].append(kwargs)
        return {"id": file_id}

    def set_file_status(fid, status):
        calls["status"].append((fid, status))

    def get_file(fid, uid):
        return {"id": fid, "filename": "a.md", "file_type": file_type, "status": "ready"}

    monkeypatch.setattr(knowledge_service.pg_client, "create_file_record", create_file_record)
    monkeypatch.setattr(knowledge_service.pg_client, "set_file_status", set_file_status)
    monkeypatch.setattr(knowledge_service.pg_client, "get_file", get_file)
    return calls


def test_upload_and_ingest_success(svc_settings, monkeypatch, tmp_path):
    calls = _mock_pg_for_upload(monkeypatch, file_id="fid-1", file_type="md")
    monkeypatch.setattr(knowledge_service.rag_service, "ingest_file", lambda fid, path, uid: 3)

    result = upload_and_ingest("a.md", b"# hello", user_id="u1")

    assert result["chunk_count"] == 3
    assert result["file"]["id"] == "fid-1"
    # 落盘文件名用 file_id 而非原始文件名，防重名/路径穿越
    assert (tmp_path / "fid-1.md").read_bytes() == b"# hello"
    # chunk_count > 0 → 状态置为 ready
    assert calls["status"] == [("fid-1", "ready")]


def test_upload_and_ingest_zero_chunks_marks_error(svc_settings, monkeypatch):
    calls = _mock_pg_for_upload(monkeypatch)
    monkeypatch.setattr(knowledge_service.rag_service, "ingest_file", lambda fid, path, uid: 0)

    result = upload_and_ingest("a.md", b"content", user_id="u1")

    assert result["chunk_count"] == 0
    # 未切出有效片段 → 状态置为 error
    assert calls["status"] == [("fid-1", "error")]


def test_upload_and_ingest_ingest_failure_marks_error_and_reraises(svc_settings, monkeypatch):
    calls = _mock_pg_for_upload(monkeypatch)

    def boom(fid, path, uid):
        raise RuntimeError("向量化失败")

    monkeypatch.setattr(knowledge_service.rag_service, "ingest_file", boom)

    with pytest.raises(RuntimeError, match="向量化失败"):
        upload_and_ingest("a.md", b"content", user_id="u1")

    # 异常前先置 error，便于排查
    assert calls["status"] == [("fid-1", "error")]


def test_upload_and_ingest_validation_error_skips_pg(svc_settings, monkeypatch):
    calls = _mock_pg_for_upload(monkeypatch)

    # 非法扩展名 → 校验阶段即抛错，不应触达建记录/落盘
    with pytest.raises(ValueError, match="不支持的文件类型"):
        upload_and_ingest("virus.exe", b"payload", user_id="u1")

    assert calls["created"] == []
    assert calls["status"] == []


# ============ delete_file ============


def test_delete_file_not_found_raises(svc_settings, monkeypatch):
    monkeypatch.setattr(knowledge_service.pg_client, "get_file", lambda fid, uid: None)
    with pytest.raises(ValueError, match="文件不存在"):
        delete_file("missing", "u1")


def test_delete_file_success(svc_settings, monkeypatch, tmp_path):
    monkeypatch.setattr(
        knowledge_service.pg_client,
        "get_file",
        lambda fid, uid: {"id": fid, "file_type": "md"},
    )
    monkeypatch.setattr(knowledge_service.milvus_client, "delete_by_file", lambda fid, uid: 7)

    deleted_records = []
    monkeypatch.setattr(
        knowledge_service.pg_client,
        "delete_file_record",
        lambda fid, uid: deleted_records.append((fid, uid)),
    )

    # 预置磁盘文件，验证被清理
    (tmp_path / "fid-1.md").write_bytes(b"x")

    result = delete_file("fid-1", "u1")

    assert result == {"file_id": "fid-1", "deleted_vectors": 7}
    assert deleted_records == [("fid-1", "u1")]
    assert not (tmp_path / "fid-1.md").exists()


def test_delete_file_continues_when_milvus_fails(svc_settings, monkeypatch):
    monkeypatch.setattr(
        knowledge_service.pg_client,
        "get_file",
        lambda fid, uid: {"id": fid, "file_type": "md"},
    )

    def boom(fid, uid):
        raise RuntimeError("Milvus 不可用")

    monkeypatch.setattr(knowledge_service.milvus_client, "delete_by_file", boom)

    deleted_records = []
    monkeypatch.setattr(
        knowledge_service.pg_client,
        "delete_file_record",
        lambda fid, uid: deleted_records.append((fid, uid)),
    )

    result = delete_file("fid-1", "u1")

    # 向量删除失败仍继续清理元数据，deleted_vectors 记为 0
    assert result == {"file_id": "fid-1", "deleted_vectors": 0}
    assert deleted_records == [("fid-1", "u1")]


# ============ list_files ============


def test_list_files_delegates_to_pg(svc_settings, monkeypatch):
    rows = [{"id": "f1", "filename": "a.md", "status": "ready"}]
    monkeypatch.setattr(knowledge_service.pg_client, "list_files", lambda uid: rows)
    assert list_files("u1") == rows
