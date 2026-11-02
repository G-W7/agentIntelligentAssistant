"""FastAPI 应用入口：uvicorn app.main:app --reload"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.endpoints import router
from app.config import get_settings
from app.core import observability
from app.db import milvus_client, pg_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期钩子。

    启动阶段：配置日志 → 初始化 PostgreSQL 建表 → 初始化 Milvus collection
    → 创建上传目录；关闭阶段：释放 PG 连接池。
    """
    settings = get_settings()
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    # 依赖服务未就绪时只告警不中断启动，保证 /docs 与 /api/health 始终可访问
    try:
        pg_client.init_db()
    except Exception:
        logger.warning("PostgreSQL 初始化失败，历史与知识库接口将返回 503", exc_info=True)

    try:
        milvus_client.init_collection()
    except Exception:
        logger.warning("Milvus 初始化失败，RAG 检索将不可用", exc_info=True)

    observability.init_langfuse()

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    yield
    observability.shutdown_langfuse()
    pg_client.close_db()
    milvus_client.close_client()


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="多 Agent 协作 + RAG + 联网搜索的智能助手后端",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    # 通配来源下开启凭证是无效且不安全的组合，浏览器会直接拒绝
    allow_credentials="*" not in settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(router)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    """根路由：返回服务名与文档 / 健康检查入口的导航信息。"""
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "health": "/api/health",
    }
