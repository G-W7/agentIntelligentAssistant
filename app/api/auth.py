"""认证路由：注册、登录、获取当前用户。

密码经 bcrypt 哈希后落库，登录成功签发 JWT；/me 用于前端刷新后恢复登录态。
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.core import security
from app.db import pg_client
from app.models.schemas import LoginRequest, RegisterRequest, TokenResponse, UserOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _to_user_out(user: dict[str, Any]) -> UserOut:
    """把数据库用户行转为对外用户模型（剔除 password_hash）。"""
    return UserOut(id=user["id"], username=user["username"], created_at=user.get("created_at"))


def _issue_token(user: dict[str, Any]) -> TokenResponse:
    """为已认证用户签发访问令牌并组装响应体。"""
    token = security.create_access_token(user["id"], user["username"])
    return TokenResponse(access_token=token, user=_to_user_out(user))


@router.post("/register", response_model=TokenResponse, summary="注册新用户")
def register(payload: RegisterRequest) -> TokenResponse:
    """注册接口：哈希密码后创建用户，成功即签发令牌自动登录。

    用户名已存在返回 409；依赖服务不可用返回 503。
    """
    password_hash = security.hash_password(payload.password)
    try:
        user = pg_client.create_user(payload.username, password_hash)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"依赖服务不可用：{exc}") from exc

    if user is None:
        raise HTTPException(status_code=409, detail="用户名已被占用")

    logger.info("新用户注册：%s", payload.username)
    return _issue_token(user)


@router.post("/login", response_model=TokenResponse, summary="用户登录")
def login(payload: LoginRequest) -> TokenResponse:
    """登录接口：校验用户名密码，成功签发 JWT。

    用户名或密码错误统一返回 401，避免暴露用户是否存在。
    """
    try:
        user = pg_client.get_user_by_username(payload.username)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"依赖服务不可用：{exc}") from exc

    if user is None or not security.verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    return _issue_token(user)


@router.get("/me", response_model=UserOut, summary="获取当前登录用户")
def me(current_user: dict[str, Any] = Depends(get_current_user)) -> UserOut:
    """返回令牌对应的用户信息，供前端刷新页面后恢复登录态。"""
    return _to_user_out(current_user)
