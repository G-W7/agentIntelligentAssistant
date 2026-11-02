"""FastAPI 鉴权依赖：从 Bearer 令牌解析当前用户。

用 HTTPBearer 提取 Authorization 头，解码校验后回查数据库确认用户仍存在，
把 {id, username} 注入受保护端点。auto_error=False 便于自定义 401 文案。
"""

import logging
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core import security
from app.db import pg_client

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False, description="登录后获取的 JWT 访问令牌")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    """校验 Bearer 令牌并返回当前用户；缺失 / 无效 / 用户不存在均抛 401。"""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供登录凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = security.decode_access_token(credentials.credentials)
    except security.AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user_id = payload["sub"]
    user = pg_client.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被删除",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
