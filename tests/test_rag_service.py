"""app/services/rag_service.py 的单元测试：切片、上下文拼接与重排序降级。

只覆盖不依赖 Milvus / Embedding 网络的纯逻辑部分，
rerank 通过替换 get_reranker 返回的假对象来验证成功与异常降级两条路径。
"""

from app.services import rag_service
from app.services.rag_service import (
    ChunkHit,
    TextSegment,
    chunk_segments,
    format_context,
    rerank_hits,
)


# ---------- chunk_segments ----------


def test_chunk_segments_prepends_header_path():
    markdown = "# 标题一\n\n正文内容 A。\n\n## 子标题\n\n正文内容 B。"
    chunks = chunk_segments([TextSegment(text=markdown)])
    assert chunks
    # 带标题层级的切片应把标题路径作为前缀 [h1 > h2]
    assert any(c["content"].startswith("[") for c in chunks)
    assert any("标题一" in c["content"] for c in chunks)


def test_chunk_segments_preserves_page():
    chunks = chunk_segments([TextSegment(text="# H\n\n内容", page=7)])
    assert all(c["page"] == 7 for c in chunks)


def test_chunk_segments_skips_empty_pieces():
    # 全空白内容不应产出切片
    assert chunk_segments([TextSegment(text="   \n\n  ")]) == []


def test_chunk_segments_no_header_has_no_prefix():
    chunks = chunk_segments([TextSegment(text="一段没有标题的普通文本。")])
    assert len(chunks) == 1
    assert not chunks[0]["content"].startswith("[")


# ---------- format_context ----------


def test_format_context_numbers_and_locations():
    hits = [
        ChunkHit(content="内容A", source_file_id="abcdefgh1234", score=0.9, page=3),
        ChunkHit(content="内容B", source_file_id="zzzzzzzz9999", score=0.5, page=None),
    ]
    ctx = format_context(hits)
    assert "[片段1]" in ctx
    assert "[片段2]" in ctx
    # 文件 ID 只截取前 8 位
    assert "abcdefgh" in ctx
    assert "第 3 页" in ctx
    # 无页码的片段不应出现"第 None 页"
    assert "None" not in ctx


def test_format_context_empty_hits():
    assert format_context([]) == ""


# ---------- rerank_hits ----------


def test_rerank_hits_empty_returns_empty():
    assert rerank_hits("q", [], top_n=3) == []


def test_rerank_hits_success_reorders_and_sets_score(monkeypatch):
    hits = [
        {"content": "doc0", "source_file_id": "f0", "score": 0.1},
        {"content": "doc1", "source_file_id": "f1", "score": 0.2},
        {"content": "doc2", "source_file_id": "f2", "score": 0.3},
    ]

    class FakeReranker:
        def rerank(self, query, documents, top_n):
            # 返回 (原始下标, 分数)，故意把 doc2 排到最前
            return [(2, 0.99), (0, 0.88)]

    monkeypatch.setattr(rag_service, "get_reranker", lambda: FakeReranker())

    result = rerank_hits("query", hits, top_n=2)
    assert [r["content"] for r in result] == ["doc2", "doc0"]
    assert result[0]["score"] == 0.99
    assert result[1]["score"] == 0.88


def test_rerank_hits_ignores_out_of_range_index(monkeypatch):
    hits = [{"content": "doc0", "source_file_id": "f0", "score": 0.1}]

    class FakeReranker:
        def rerank(self, query, documents, top_n):
            return [(5, 0.9), (0, 0.8)]  # 下标 5 越界，应被丢弃

    monkeypatch.setattr(rag_service, "get_reranker", lambda: FakeReranker())

    result = rerank_hits("query", hits, top_n=2)
    assert [r["content"] for r in result] == ["doc0"]


def test_rerank_hits_falls_back_on_exception(monkeypatch):
    hits = [
        {"content": "doc0", "source_file_id": "f0", "score": 0.1},
        {"content": "doc1", "source_file_id": "f1", "score": 0.2},
    ]

    class BrokenReranker:
        def rerank(self, query, documents, top_n):
            raise RuntimeError("rerank 服务不可用")

    monkeypatch.setattr(rag_service, "get_reranker", lambda: BrokenReranker())

    # 异常时降级为原始顺序截断 top_n
    result = rerank_hits("query", hits, top_n=1)
    assert result == [{"content": "doc0", "source_file_id": "f0", "score": 0.1}]
