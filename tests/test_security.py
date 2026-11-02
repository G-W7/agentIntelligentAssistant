"""app/core/security.py 的单元测试：密码哈希与 JWT 签发/校验。

通过 monkeypatch 把 security 模块内的 get_settings 替换成可控配置，
使令牌测试不依赖真实 .env，并能构造过期令牌等边界场景。
"""

import jwt
import pytest

from app.core import security
from app.core.security import AuthError


@pytest.fixture
def auth_settings(monkeypatch, make_settings):
    """把 security.get_settings 固定为已知密钥与有效期的配置。"""
    settings = make_settings(
        jwt_secret_key="unit-test-secret-key-0123456789abcdef",
        jwt_algorithm="HS256",
        access_token_expire_minutes=60,
    )
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    return settings


# ---------- 密码哈希 ----------


def test_hash_password_is_not_plaintext():
    hashed = security.hash_password("P@ssw0rd")
    assert hashed != "P@ssw0rd"
    assert hashed.startswith("$2")  # bcrypt 前缀


def test_hash_password_is_salted():
    # 相同明文两次哈希应得到不同盐，结果不相等
    assert security.hash_password("same") != security.hash_password("same")


def test_verify_password_roundtrip():
    hashed = security.hash_password("correct horse battery staple")
    assert security.verify_password("correct horse battery staple", hashed) is True
    assert security.verify_password("wrong password", hashed) is False


def test_verify_password_supports_long_password():
    # 预哈希（SHA-256）绕开 bcrypt 72 字节上限，超长密码仍可校验
    long_pw = "a" * 200
    hashed = security.hash_password(long_pw)
    assert security.verify_password(long_pw, hashed) is True


def test_verify_password_invalid_hash_returns_false():
    # 哈希损坏时应返回 False 而非抛异常
    assert security.verify_password("any", "not-a-valid-bcrypt-hash") is False


# ---------- JWT ----------


def test_create_and_decode_token_roundtrip(auth_settings):
    token = security.create_access_token(user_id="u-123", username="alice")
    payload = security.decode_access_token(token)
    assert payload["sub"] == "u-123"
    assert payload["username"] == "alice"
    assert payload["exp"] > payload["iat"]


def test_decode_expired_token_raises(auth_settings):
    # 直接构造一个已过期的令牌（exp 在过去）
    expired = jwt.encode(
        {"sub": "u-1", "username": "bob", "iat": 0, "exp": 1},
        auth_settings.jwt_secret_key,
        algorithm=auth_settings.jwt_algorithm,
    )
    with pytest.raises(AuthError, match="过期"):
        security.decode_access_token(expired)


def test_decode_invalid_signature_raises(make_settings, monkeypatch):
    # 用密钥 A 签发，再用密钥 B 校验，应判为无效凭证
    # 密钥长度 ≥ 32 字节，避免 PyJWT 的 InsecureKeyLengthWarning
    sign_settings = make_settings(
        jwt_secret_key="unit-test-sign-key-A-0123456789abcdef",
        jwt_algorithm="HS256",
    )
    token = jwt.encode(
        {"sub": "u-1"}, sign_settings.jwt_secret_key, algorithm="HS256"
    )

    verify_settings = make_settings(
        jwt_secret_key="unit-test-verify-key-B-0123456789abcdef",
        jwt_algorithm="HS256",
    )
    monkeypatch.setattr(security, "get_settings", lambda: verify_settings)

    with pytest.raises(AuthError, match="无效"):
        security.decode_access_token(token)


def test_decode_token_missing_sub_raises(auth_settings):
    token = jwt.encode(
        {"username": "no-sub"},
        auth_settings.jwt_secret_key,
        algorithm=auth_settings.jwt_algorithm,
    )
    with pytest.raises(AuthError, match="用户标识"):
        security.decode_access_token(token)


def test_decode_garbage_token_raises(auth_settings):
    with pytest.raises(AuthError):
        security.decode_access_token("this.is.not-a-jwt")
