"""全局配置：所有可调参数集中在此，通过 .env 或环境变量注入。"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 知识库文件扩展名白名单，上传校验时使用
ALLOWED_EXTENSIONS = {".pdf", ".md", ".markdown", ".txt"}


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
    openai_base_url: str | None = None
    chat_model: str = "gpt-4o-mini"
    temperature: float = 0.2

    # Embedding：维度必须与 Milvus collection 一致，改动后需重建 collection
    embedding_provider: str = "openai"  # openai | huggingface | dashscope
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 1024
    hf_embedding_model: str = "BAAI/bge-m3"
    embedding_batch_size: int = 32

    # DashScope / 千问 embedding（EMBEDDING_PROVIDER=dashscope 时生效）
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    # 同步接口单批上限 25，v3/v4 建议 10 以内
    dashscope_batch_size: int = 10

    # 联网搜索
    tavily_api_key: str = ""
    tavily_max_results: int = 5

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "agent"
    postgres_password: str = "agent"
    postgres_db: str = "agent_assistant"
    postgres_pool_size: int = 8

    # Milvus
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection: str = "agent_knowledge_base"
    milvus_top_k: int = 4

    # 文档切片
    chunk_size: int = 1000
    chunk_overlap: int = 200
    upload_dir: Path = PROJECT_ROOT / "data" / "uploads"
    max_upload_mb: int = 20

    # 会话
    history_window: int = 20

    # 前端 / 跨域
    cors_origins: str = "*"

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
