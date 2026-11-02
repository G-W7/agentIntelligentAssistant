"""全局配置：所有可调参数集中在此，通过 .env 或环境变量注入。"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 知识库文件扩展名白名单，上传校验时使用
ALLOWED_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt", ".docx", ".pptx", ".xlsx", ".png", ".jpg", ".jpeg"}


class Settings(BaseSettings):
    """全局配置模型：字段值优先从 .env / 环境变量读取，未提供时用默认值。"""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Agent 智能助手"
    debug: bool = False

    # LLM
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    # 默认对齐 .env；deepseek-flash 的思考模式在 llm.py 中已显式关闭
    chat_model: str = "deepseek-flash"
    temperature: float = 0.2

    # Embedding：千问 DashScope，维度必须与 Milvus collection 一致，改动后需重建 collection
    embedding_model: str = "qwen3.7-text-embedding-flash"
    embedding_dimensions: int = 1024

    # DashScope / 千问 embedding
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    # 同步接口单批上限 25，v3/v4 建议 10 以内
    dashscope_batch_size: int = 10

    # Rerank：千问 DashScope 重排序模型（gte-rerank 已于 2026-05 下线，改用 qwen3-rerank）
    # 开启后：混合检索先粗召回 rerank_recall 条，再由 rerank 模型精排取 top_k
    rerank_enabled: bool = True
    rerank_model: str = "qwen3.7-text-rerank"
    rerank_recall: int = 20

    # 联网搜索
    tavily_api_key: str = ""
    tavily_max_results: int = 5

    # MinerU 文档解析
    mineru_token: str = ""

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = ""
    postgres_db: str = "postgres"
    postgres_pool_size: int = 8

    # Milvus
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection: str = "agent_knowledge_base"
    milvus_top_k: int = 4
    milvus_sparse_weight: float = 0.3
    milvus_dense_weight: float = 0.7

    # 文档切片
    chunk_size: int = 1200
    chunk_overlap: int = 240
    upload_dir: Path = PROJECT_ROOT / "data" / "uploads"
    max_upload_mb: int = 20

    # 会话
    history_window: int = 20

    # 认证（JWT）：生产环境务必用环境变量注入一个足够随机的 jwt_secret_key（≥ 32 字节）
    jwt_secret_key: str = "change-me-in-production-use-a-random-secret-key"
    jwt_algorithm: str = "HS256"
    # 访问令牌有效期（分钟），默认 7 天
    access_token_expire_minutes: int = 60 * 24 * 7

    # 前端 / 跨域
    backend_base_url: str = "http://127.0.0.1:8000"
    cors_origins: str = "*"

    # Langfuse 可观测性（可选）：开关打开且密钥齐全时才启用，否则退化为 no-op
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_base_url: str = "https://cloud.langfuse.com"
    # 采样率 0~1，生产高流量时可调低以控制上报量
    langfuse_sample_rate: float = 1.0

    @property
    def postgres_dsn(self) -> str:
        """拼接 psycopg2 可用的 PostgreSQL 连接串。"""
        return (
            f"host={self.postgres_host} port={self.postgres_port} "
            f"user={self.postgres_user} password={self.postgres_password} "
            f"dbname={self.postgres_db}"
        )

    @property
    def milvus_uri(self) -> str:
        """拼接 Milvus 的 HTTP 连接地址。"""
        return f"http://{self.milvus_host}:{self.milvus_port}"

    @property
    def cors_origin_list(self) -> list[str]:
        """把逗号分隔的 CORS_ORIGINS 字符串拆成来源列表。"""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        """上传大小上限，由 MB 换算为字节。"""
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """配置获取入口：lru_cache 保证整个进程只解析一次 .env，各处共享同一实例。"""
    return Settings()
