"""pytest 全局配置与共享 fixture。

作用：
1. 把项目根目录加入 sys.path，保证测试内 `import app.*` 正常（无需安装包）；
2. 提供各测试文件复用的 fixture（如伪造的数据库行、可控的 Settings）。
"""

import sys
from pathlib import Path

import pytest

# tests/ 的上一级即项目根目录，加入 sys.path 后可直接 import app
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Settings  # noqa: E402


@pytest.fixture
def make_settings():
    """构造一个不读取 .env、字段完全可控的 Settings 工厂。

    用法：settings = make_settings(jwt_secret_key="x", chunk_size=100)
    仅用于纯逻辑测试，避免依赖真实环境变量导致的偶发失败。
    """

    def _factory(**overrides) -> Settings:
        # _env_file=None 强制忽略 .env，只用默认值 + overrides，保证测试确定性
        return Settings(_env_file=None, **overrides)

    return _factory


@pytest.fixture
def fake_history_rows():
    """伪造 pg_client.list_messages 返回的历史消息行（时间正序）。"""
    return [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好，有什么可以帮你？"},
        {"role": "user", "content": "介绍一下 RAG"},
    ]
