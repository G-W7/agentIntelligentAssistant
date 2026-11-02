"""app/config.py 的单元测试：验证派生属性（DSN / URI / CORS / 上传上限）。"""

from app.config import ALLOWED_EXTENSIONS


def test_postgres_dsn_contains_all_fields(make_settings):
    settings = make_settings(
        postgres_host="db",
        postgres_port=6543,
        postgres_user="alice",
        postgres_password="secret",
        postgres_db="appdb",
    )
    dsn = settings.postgres_dsn
    assert "host=db" in dsn
    assert "port=6543" in dsn
    assert "user=alice" in dsn
    assert "password=secret" in dsn
    assert "dbname=appdb" in dsn


def test_milvus_uri_is_http(make_settings):
    settings = make_settings(milvus_host="milvus", milvus_port=19530)
    assert settings.milvus_uri == "http://milvus:19530"


def test_cors_origin_list_splits_and_strips(make_settings):
    settings = make_settings(cors_origins="http://a.com, http://b.com ,")
    # 去除首尾空格并丢弃空串
    assert settings.cors_origin_list == ["http://a.com", "http://b.com"]


def test_cors_origin_list_wildcard(make_settings):
    settings = make_settings(cors_origins="*")
    assert settings.cors_origin_list == ["*"]


def test_max_upload_bytes_converts_mb(make_settings):
    settings = make_settings(max_upload_mb=5)
    assert settings.max_upload_bytes == 5 * 1024 * 1024


def test_allowed_extensions_are_lowercase_with_dot():
    assert ".pdf" in ALLOWED_EXTENSIONS
    # 白名单应统一小写并带前导点，避免上传校验漏判
    assert all(ext.startswith(".") and ext == ext.lower() for ext in ALLOWED_EXTENSIONS)
