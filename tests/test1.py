
from app.core.llm import get_embeddings

emb = get_embeddings()
print("单条:", len(emb.embed_query("测试一下")))
print("批量:", [len(v) for v in emb.embed_documents(["第一段", "第二段", "第三段"])])
