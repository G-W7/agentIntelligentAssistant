"""RAG 核心流程：文档解析 → 切片 → 向量化 → 写入 Milvus → 检索。

对应设计文档 4.2。
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.core.llm import get_embeddings
from app.db import milvus_client

logger = logging.getLogger(__name__)


@dataclass
class TextSegment:
    """一段带出处信息的原始文本，PDF 按页切分以保留页码。"""

    text: str
    page: int | None = None


@dataclass
class ChunkHit:
    """一次向量检索命中的切片：内容、来源文件 ID、相似度分数与页码。"""

    content: str
    source_file_id: str
    score: float
    page: int | None = None


def extract_segments(path: Path) -> list[TextSegment]:
    """文档解析：使用 MinerU API 将文档转为高质量 Markdown。

    支持 PDF、图片、DOCX、PPTX、XLSX、md/txt 等格式。
    MinerU 会保留文档结构、公式（LaTeX）和表格。
    """
    settings = get_settings()

    if not settings.mineru_token:
        raise ValueError("未配置 MINERU_TOKEN，无法使用 MinerU 解析文档")

    from mineru import MinerU

    suffix = path.suffix.lower()

    if suffix in {".md", ".markdown", ".txt"}:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        return [TextSegment(text=text)] if text else []

    try:
        with MinerU(settings.mineru_token) as client:
            result = client.extract(str(path))
    except Exception as e:
        logger.error("MinerU 解析文件 %s 异常：%s", path.name, e)
        raise ValueError(f"MinerU 文档解析失败：{e}") from e

    if result.state != "done" or not result.markdown:
        logger.warning("MinerU 解析文件 %s 未成功，state=%s", path.name, result.state)
        return []

    markdown = result.markdown.strip()
    if not markdown:
        return []

    segments: list[TextSegment] = []
    pages = markdown.split("\n\n---\n\n")
    if len(pages) > 1:
        for number, page_text in enumerate(pages, start=1):
            page_text = page_text.strip()
            if page_text:
                segments.append(TextSegment(text=page_text, page=number))
    else:
        segments.append(TextSegment(text=markdown))

    return segments


def chunk_segments(segments: list[TextSegment]) -> list[dict]:
    """文本切片：按配置的 chunk_size / chunk_overlap 递归切分每个段落。

    分隔符优先级兼顾中英文（段落 → 换行 → 中文句号等 → 英文句号 → 空格），
    每个切片携带原段落的页码；返回 [{content, page}] 列表。
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    settings = get_settings()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        separators=["\n\n", "\n", "。", "！", "？", ".", " ", ""],
    )

    chunks: list[dict] = []
    for segment in segments:
        for piece in splitter.split_text(segment.text):
            piece = piece.strip()
            if piece:
                chunks.append({"content": piece, "page": segment.page})
    return chunks


def embed_documents(texts: list[str]) -> list[list[float]]:
    """批量向量化：按 dashscope_batch_size 分批调用 Embedding 模型，避免单次请求过大。"""
    if not texts:
        return []
    settings = get_settings()
    embeddings = get_embeddings()
    vectors: list[list[float]] = []
    step = settings.dashscope_batch_size
    for start in range(0, len(texts), step):
        vectors.extend(embeddings.embed_documents(texts[start : start + step]))
    return vectors


def embed_query(text: str) -> list[float]:
    """把单条查询文本向量化，用于检索时的相似度计算。"""
    return get_embeddings().embed_query(text)


def ingest_file(file_id: str, path: Path) -> int:
    """把单个文件写入向量库，返回切片数量。"""
    milvus_client.init_collection()

    chunks = chunk_segments(extract_segments(path))
    if not chunks:
        logger.warning("文件 %s 未解析出有效文本", path.name)
        return 0

    vectors = embed_documents([c["content"] for c in chunks])
    rows = []
    for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
        row = {
            "pk": f"{file_id}_{index}",
            "vector": vector,
            "content": chunk["content"],
            "source_file_id": file_id,
        }
        if chunk["page"] is not None:
            row["page"] = chunk["page"]
        rows.append(row)

    count = milvus_client.insert_chunks(rows)
    logger.info("文件 %s 已入库，共 %d 个切片", file_id, count)
    return count


def retrieve_chunks(
    query: str, top_k: int | None = None, file_ids: list[str] | None = None
) -> list[ChunkHit]:
    """向量检索 Top-K 片段，可按文件 ID 过滤。"""
    hits = milvus_client.search(
        query_vector=embed_query(query), top_k=top_k, file_ids=file_ids
    )
    return [ChunkHit(**hit) for hit in hits]


def format_context(hits: list[ChunkHit]) -> str:
    """把检索结果拼成带编号的 Prompt 上下文，供 LLM 引用。"""
    blocks = []
    for index, hit in enumerate(hits, start=1):
        location = f"，第 {hit.page} 页" if hit.page else ""
        blocks.append(f"[片段{index}] (文档 {hit.source_file_id[:8]}{location})\n{hit.content}")
    return "\n\n".join(blocks)
