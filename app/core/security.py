"""认证安全工具：密码哈希（bcrypt）与 JWT 签发校验（PyJWT）。

集中在此处封装，路由层与依赖层都从这里取，避免密钥与算法散落各处。
"""

import base64
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.config import get_settings

logger = logging.getLogger(__name__)

# JWT subject 声明的键名，解码后据此定位用户
_SUBJECT_KEY = "sub"


class AuthError(Exception):
    """认证相关错误：令牌无效 / 过期 / 缺少必要声明。

    路由层与依赖层捕获后统一转成 401，避免把内部细节暴露给客户端。
    """


def _prehash(password: str) -> bytes:
    """先对密码做 SHA-256 再 base64，得到固定 44 字节的输入。

    bcrypt 有 72 字节硬上限且对空字节敏感，预哈希可安全支持任意长度密码，
    避免直接截断导致的碰撞风险。
    """
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(plain: str) -> str:
    """把明文密码哈希为不可逆的 bcrypt 串，用于落库。"""
    return bcrypt.hashpw(_prehash(plain), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码与库中哈希是否匹配；哈希损坏时返回 False 而非抛异常。"""
    try:
        return bcrypt.checkpw(_prehash(plain), hashed.encode("utf-8"))
    except ValueError:
        logger.warning("密码哈希校验失败：哈希格式非法")
        return False


def create_access_token(user_id: str, username: str) -> str:
    """签发访问令牌：sub 存 user_id，附带 username 便于前端展示。

    过期时间由 ACCESS_TOKEN_EXPIRE_MINUTES 控制，使用 UTC 时间戳。
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        _SUBJECT_KEY: user_id,
        "username": username,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """解码并校验令牌，返回 payload；无效或过期抛 AuthError。"""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("登录已过期，请重新登录") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("无效的登录凭证") from exc

    if not payload.get(_SUBJECT_KEY):
        raise AuthError("令牌缺少用户标识")
    return payload
