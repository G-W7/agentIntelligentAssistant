"""Agent worker 节点测试：用假 LLM 与假工具替换外部调用，验证各节点的分支逻辑。

覆盖 router_node 结构化路由、rag_worker 命中/未命中、search_worker 正常/无结果/异常降级、
chat_worker 直答。所有节点都是 async，pytest-asyncio（auto 模式）直接驱动。
"""

from langchain_core.messages import AIMessage, HumanMessage

from app.core import agents
from app.core.agents import RouteDecision
from app.core.tools import SearchOutcome, WebResult
from app.services.rag_service import ChunkHit


class FakeStructured:
    """假的 with_structured_output 结果：ainvoke 直接返回预置决策。"""

    def __init__(self, decision):
        self._decision = decision

    async def ainvoke(self, messages):
        return self._decision


class FakeChatModel:
    """假对话模型：ainvoke 返回固定 AIMessage，with_structured_output 返回固定决策。"""

    def __init__(self, answer="模型回答", decision=None):
        self._answer = answer
        self._decision = decision
        self.invoked = False

    async def ainvoke(self, messages):
        self.invoked = True
        return AIMessage(content=self._answer)

    def with_structured_output(self, schema, method=None):
        return FakeStructured(self._decision)


def _forbid_llm():
    """构造一个一旦被调用就失败的 get_chat_model，用于断言未走 LLM 分支。"""

    def _factory():
        raise AssertionError("不应调用 LLM")

    return _factory


# ============ router_node ============


async def test_router_node_returns_decision(monkeypatch):
    decision = RouteDecision(destination="rag", reason="需要查文档")
    monkeypatch.setattr(
        agents, "get_chat_model", lambda: FakeChatModel(decision=decision)
    )
    state = {"messages": [HumanMessage(content="根据文档说说规定")]}
    result = await agents.router_node(state)
    assert result == {"route": "rag", "route_reason": "需要查文档"}


# ============ rag_worker ============


async def test_rag_worker_no_hits_skips_llm(monkeypatch):
    monkeypatch.setattr(agents.rag_service, "retrieve_chunks", lambda q, uid: [])
    # 未命中时不应调用 LLM
    monkeypatch.setattr(agents, "get_chat_model", _forbid_llm())

    state = {"messages": [HumanMessage(content="随便问")], "user_id": "u1"}
    result = await agents.rag_worker(state)

    assert isinstance(result["messages"][0], AIMessage)
    assert "未检索到" in result["messages"][0].content
    assert result["sources"] == []


async def test_rag_worker_with_hits_builds_sources(monkeypatch):
    hits = [
        ChunkHit(
            content="x" * 400,  # 超过 300，应被截断
            source_file_id="file-abc-123",
            score=0.87654,
            page=2,
        )
    ]
    monkeypatch.setattr(agents.rag_service, "retrieve_chunks", lambda q, uid: hits)
    monkeypatch.setattr(agents.rag_service, "format_context", lambda h: "拼接的上下文")
    fake = FakeChatModel(answer="基于文档的答案")
    monkeypatch.setattr(agents, "get_chat_model", lambda: fake)

    state = {"messages": [HumanMessage(content="问题")], "user_id": "u1"}
    result = await agents.rag_worker(state)

    assert fake.invoked is True
    assert result["messages"][0].content == "基于文档的答案"
    source = result["sources"][0]
    assert source["kind"] == "knowledge"
    assert source["file_id"] == "file-abc-123"
    assert source["page"] == 2
    assert source["score"] == 0.8765  # round(_, 4)
    assert len(source["content"]) == 300  # 截断到 300


# ============ search_worker ============


async def test_search_worker_error_degrades(monkeypatch):
    def boom(query):
        raise RuntimeError("Tavily 不可用")

    monkeypatch.setattr(agents, "web_search", boom)
    monkeypatch.setattr(agents, "get_chat_model", _forbid_llm())

    state = {"messages": [HumanMessage(content="今天天气")]}
    result = await agents.search_worker(state)

    assert "联网搜索暂时不可用" in result["messages"][0].content
    assert result["sources"] == []


async def test_search_worker_no_results(monkeypatch):
    monkeypatch.setattr(agents, "web_search", lambda query: SearchOutcome(results=[]))
    monkeypatch.setattr(agents, "get_chat_model", _forbid_llm())

    state = {"messages": [HumanMessage(content="冷门问题")]}
    result = await agents.search_worker(state)

    assert "没有找到相关的搜索结果" in result["messages"][0].content
    assert result["sources"] == []


async def test_search_worker_success_builds_sources(monkeypatch):
    outcome = SearchOutcome(
        results=[
            WebResult(title="标题A", url="http://a", content="正文A", score=0.91234),
            WebResult(title="标题B", url="http://b", content="y" * 400, score=0.5),
        ],
        answer="官方摘要",
    )
    monkeypatch.setattr(agents, "web_search", lambda query: outcome)
    fake = FakeChatModel(answer="根据搜索结果")
    monkeypatch.setattr(agents, "get_chat_model", lambda: fake)

    state = {"messages": [HumanMessage(content="最新新闻")]}
    result = await agents.search_worker(state)

    assert fake.invoked is True
    assert result["messages"][0].content == "根据搜索结果"
    sources = result["sources"]
    assert len(sources) == 2
    assert sources[0]["kind"] == "web"
    assert sources[0]["index"] == 1
    assert sources[0]["title"] == "标题A"
    assert sources[0]["url"] == "http://a"
    assert sources[0]["score"] == 0.9123  # round(_, 4)
    assert sources[1]["index"] == 2
    assert len(sources[1]["content"]) == 300  # 截断


# ============ chat_worker ============


async def test_chat_worker_returns_answer_no_sources(monkeypatch):
    fake = FakeChatModel(answer="你好，很高兴帮你")
    monkeypatch.setattr(agents, "get_chat_model", lambda: fake)

    state = {"messages": [HumanMessage(content="你好")]}
    result = await agents.chat_worker(state)

    assert fake.invoked is True
    assert result["messages"][0].content == "你好，很高兴帮你"
    assert result["sources"] == []
