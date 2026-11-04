"""FastAPI 应用入口：uvicorn app.main:app --reload"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.endpoints import router
from app.config import get_settings
from app.core import observability
from app.db import checkpointer, milvus_client, pg_client
from app.skills import mcp as mcp_skill
from app.skills import registry

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期钩子。

    启动阶段：配置日志 → 初始化 PostgreSQL 建表 → 初始化 Checkpointer
    → 初始化 Milvus collection → 创建上传目录；关闭阶段：释放 Checkpointer 与 PG 连接池。
    """
    settings = get_settings()
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    # 发现并注册 app/skills/ 下的技能（内置 + 自定义 + MCP），使面板与路由即时可用；
    # 失败只告警不中断，保证 /docs 与 /api/health 始终可访问。
    try:
        registry.discover()
    except Exception:
        logger.warning("技能发现失败，Agent 图可能缺少工作者", exc_info=True)

    # 预热 MCP：拉一次工具列表并把工具名/简介写回 mcp 技能的 description，
    # 让主管路由 Prompt 能感知具体工具，避免「今天几号」被误判给 search。
    # 失败只告警不中断：description 保持静态兜底文案，其它技能不受影响。
    try:
        await mcp_skill.warm_up()
    except Exception:
        logger.warning("MCP 工具预热失败，路由描述可能不够精确", exc_info=True)

    # 依赖服务未就绪时只告警不中断启动，保证 /docs 与 /api/health 始终可访问
    try:
        pg_client.init_db()
    except Exception:
        logger.warning("PostgreSQL 初始化失败，历史与知识库接口将返回 503", exc_info=True)

    # 初始化 LangGraph Checkpointer（默认 AsyncPostgresSaver）：必须在事件循环内
    # 且早于任何 get_graph() 调用，以便图编译时拿到已就绪的共享单例；失败自动回退 MemorySaver。
    try:
        await checkpointer.init_checkpointer()
    except Exception:
        logger.warning("Checkpointer 初始化失败，多轮上下文可能不可用", exc_info=True)

    try:
        milvus_client.init_collection()
    except Exception:
        logger.warning("Milvus 初始化失败，RAG 检索将不可用", exc_info=True)

    observability.init_langfuse()

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    yield
    observability.shutdown_langfuse()
    await checkpointer.close_checkpointer()
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
