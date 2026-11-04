# Agent 智能助手

> 多 Agent 协作 + 可插拔技能 + RAG + 联网搜索 + MCP 工具的企业级智能助手

一个基于 **LangGraph** 编排的企业级智能问答系统。系统采用「主管—工作者」拓扑，工作者以**可插拔技能**的形式在运行时动态注册——主管据各技能描述自动将用户问题路由到 **知识库检索（RAG）**、**联网搜索**、**通用对话**、**天气查询** 或 **MCP 工具调用** 等链路，并配套 Next.js 前端、JWT 认证、混合检索重排序与 Langfuse 可观测性。

---

## ✨ 核心特性

- **多 Agent 协作**：主管节点（Supervisor）通过 LLM 结构化输出判定意图，分发到对应工作者节点；工作者采用「先确定性检索、再一次 LLM 合成」模式，比 ReAct 循环更快更稳定。
- **可插拔技能系统**：工作者以 `app/skills/` 下的独立技能文件定义，`registry.discover()` 在运行时自动发现注册；主管路由 Prompt 与图拓扑均由已启用技能动态生成——**新增一个技能文件、重启即生效，无需改动任何编排代码**。内置 `rag / search / chat`，并附天气查询自定义示例。
- **MCP 工具接入**：通过 `mcp.json` 声明外部 MCP server，`langchain-mcp-adapters` 将其工具转为 LangChain 工具，由 `mcp` 技能以 ReAct 循环按需调用（文件系统、时间、第三方 API 等）；未配置时该技能自动停用，不影响其它链路。
- **RAG 知识库问答**：文档经 MinerU 结构化解析 → Markdown 分层切片 → DashScope 向量化 → 写入 Milvus，回答严格标注 `[片段N]` 来源，杜绝编造。
- **混合检索 + 重排序**：Milvus BM25 稀疏向量 + 稠密向量加权融合粗召回，再由 `qwen3-rerank` 精排取 Top-K；rerank 异常时自动降级为原始排序。
- **联网搜索**：集成 Tavily 实时检索，回答标注 `[N]` 引用序号，来源可点击跳转。
- **持久化会话记忆**：LangGraph Checkpointer（默认 `PostgresSaver`）将多轮上下文持久化到 PostgreSQL，**支持多进程 / 多实例部署**共享同一会话状态；`chat_history` 负责前端历史展示与迁移前旧会话的上下文重建，均按 `user_id` 隔离。（`CHECKPOINT_BACKEND=memory` 可降级为进程内 `MemorySaver`，仅单实例、重启丢失）
- **流式输出**：`/api/chat/stream` 以 SSE 逐 token 推送，实时反馈路由判定、增量回答与参考来源。
- **JWT 认证**：bcrypt 哈希密码 + PyJWT 签发令牌，知识库检索按用户隔离。
- **可观测性**：可选接入 Langfuse，追踪路由准确率与调用链路（未启用时退化为 no-op）。
- **双前端**：Next.js 16 + React 19 现代 Web 前端（含「技能与工具」面板），另保留 Gradio 轻量界面。

---

## 🏗️ 系统架构

```
                         ┌──────────────────────────┐
   用户 ──► Next.js 前端  │  FastAPI (RESTful + SSE)  │
        └► Gradio 界面    │  JWT 认证 · CORS · 健康检查 │
                         └────────────┬─────────────┘
                                      │
                         ┌────────────▼─────────────┐
                         │   LangGraph 编排 (主管)    │
                         │  router_node 动态意图路由   │
                         │ 工作者 ← 技能注册表 discover │
                         └────────────┬─────────────┘
                                      │ 条件分发到已启用技能
        ┌──────────┬──────────┬───────┴────┬──────────┐
        ▼          ▼          ▼            ▼          ▼
   ┌────────┐ ┌────────┐ ┌────────┐  ┌─────────┐ ┌─────────┐
   │  rag   │ │ search │ │  chat  │  │ weather │ │   mcp   │
   │知识库检索│ │联网搜索 │ │通用对话 │  │天气查询  │ │工具调用  │
   │ Milvus │ │ Tavily │ │直接 LLM │  │Open-Meteo│ │ReAct 工具│
   └───┬────┘ └───┬────┘ └────────┘  └────┬────┘ └────┬────┘
       │          │                       │           │
       ▼          ▼                       ▼           ▼
  ┌─────────┐ ┌──────────────┐     (免费 API)   ┌──────────────┐
  │ Milvus  │ │ DeepSeek LLM │                 │ 外部 MCP      │
  │ 向量库   │ │ DashScope Emb│                 │ server(可插拔) │
  │BM25+稠密 │ └──────────────┘                 └──────────────┘
  │ +rerank │
  └────┬────┘
       │
       ▼
  ┌──────────────────────────┐
  │ PostgreSQL (用户/历史/文件/会话状态) │
  └──────────────────────────┘
```

**Agent 图拓扑**：`START → router →(条件分发)→ 各已启用技能（rag / search / chat / weather / mcp …）→ END`。工作者节点、条件边与主管路由 Prompt 均由技能注册表在运行时动态生成。

---

## 🧱 技术栈

| 分层 | 技术选型 |
| --- | --- |
| 语言 / 运行时 | Python 3.13+ · Node.js 20+ |
| Web 框架 | FastAPI · Uvicorn |
| Agent 编排 | LangChain · LangGraph（`PostgresSaver` Checkpointer 持久化会话状态） |
| 技能 / 工具 | 可插拔技能注册表 · MCP（`langchain-mcp-adapters` + ReAct 工具调用） |
| LLM | DeepSeek（`deepseek-flash`，OpenAI 兼容接口） |
| Embedding / Rerank | 千问 DashScope（`qwen3-text-embedding` / `qwen3-rerank`） |
| 向量检索 | Milvus 2.6（BM25 Function 混合检索） |
| 关系存储 | PostgreSQL 16 |
| 对象存储 | RustFS（S3 兼容，替代 MinIO） |
| 文档解析 | MinerU Open SDK |
| 联网搜索 | Tavily |
| 天气数据 | Open-Meteo（免费、无需 Key，自定义技能示例） |
| 认证 | bcrypt · PyJWT |
| 可观测性 | Langfuse（可选） |
| 前端 | Next.js 16 · React 19 · TanStack Query · Zustand · shadcn/ui · Tailwind CSS 4 |
| 依赖管理 | uv（后端）· npm（前端） |
| 容器化 | Docker Compose（etcd / RustFS / Milvus / PostgreSQL / Attu） |

---

## 📁 项目结构

```
agentIntelligentAssistant/
├── app/                        # FastAPI 后端
│   ├── api/                    # 路由层
│   │   ├── auth.py             #   注册 / 登录 / 当前用户
│   │   ├── endpoints.py        #   对话 / 上传 / 历史 / 文件 / 健康检查
│   │   └── deps.py             #   JWT 鉴权依赖
│   ├── core/                   # 核心能力
│   │   ├── agent_graph.py      #   LangGraph 图编排（工作者由技能注册表动态提供）
│   │   ├── agents.py           #   主管路由节点 + Agent 状态定义
│   │   ├── llm.py              #   LLM / Embedding / Rerank 工厂
│   │   ├── tools.py            #   Tavily 联网搜索工具
│   │   ├── mcp_client.py       #   加载 mcp.json，把 MCP server 转为 LangChain 工具
│   │   ├── security.py         #   密码哈希 + JWT 签发校验
│   │   └── observability.py    #   Langfuse 追踪
│   ├── skills/                 # 可插拔技能（每个文件 = 一个工作者）
│   │   ├── base.py             #   技能契约 Skill / SkillMetadata
│   │   ├── registry.py         #   自动发现与注册中心 + 动态路由 Prompt
│   │   ├── rag.py              #   知识库问答（内置）
│   │   ├── search.py           #   联网搜索（内置）
│   │   ├── chat.py             #   通用对话（内置，路由兜底）
│   │   ├── weather.py          #   天气查询（自定义示例，Open-Meteo）
│   │   └── mcp.py              #   MCP 工具调用（ReAct，未配置时自动停用）
│   ├── services/               # 业务逻辑
│   │   ├── chat_service.py     #   会话装载 → 调图 → 持久化（含流式）
│   │   ├── rag_service.py      #   解析 → 切片 → 向量化 → 混合检索
│   │   └── knowledge_service.py#   文件上传 / 列表 / 删除
│   ├── db/                     # 数据访问
│   │   ├── pg_client.py        #   PostgreSQL 连接池与建表
│   │   ├── checkpointer.py     #   LangGraph Checkpointer（PostgresSaver，多实例共享会话状态）
│   │   └── milvus_client.py    #   Milvus collection 与混合检索
│   ├── models/schemas.py       # Pydantic 请求 / 响应模型
│   ├── config.py               # 全局配置（.env 注入）
│   └── main.py                 # 应用入口与生命周期（技能发现 + MCP 预热）
├── frontend-next/              # Next.js 前端（主，含技能与工具面板）
├── frontend/gradio_app.py      # Gradio 前端（轻量备用）
├── data/uploads/               # 上传文件落盘目录
├── tests/                      # 测试（含 test_skills / test_mcp）
├── docker-compose.yml          # 基础设施容器编排
├── pyproject.toml              # 后端依赖（uv）
├── .env.example                # 环境变量模板
├── mcp.example.json            # MCP 服务配置模板（复制为 mcp.json）
└── README.md
```

---

## 🚀 快速开始

### 1. 前置依赖

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)（Python 包管理器）
- Node.js 20+（前端）
- Docker & Docker Compose（基础设施）
- 各类 API Key：DeepSeek、DashScope（千问）、Tavily、MinerU

### 2. 启动基础设施

```bash
docker-compose up -d
```

启动的服务：

| 服务 | 端口 | 说明 |
| --- | --- | --- |
| etcd | 2379 | Milvus 元数据协调 |
| RustFS（对象存储） | 9000 / 9001 | Milvus 底层存储，控制台 9001 |
| Milvus | 19530 / 9091 | 向量数据库 |
| PostgreSQL | 5432 | 关系数据库（用户 / 历史 / 文件 / 会话 checkpoint） |
| Attu | 3000 | Milvus 可视化管理界面 |

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 填入真实密钥，关键项：

| 变量 | 说明 |
| --- | --- |
| `DEEPSEEK_API_KEY` | 对话 LLM 密钥 |
| `DASHSCOPE_API_KEY` | 千问 Embedding / Rerank 密钥 |
| `TAVILY_API_KEY` | 联网搜索密钥 |
| `MINERU_TOKEN` | 文档解析令牌（[mineru.net](https://mineru.net) 申请） |
| `JWT_SECRET_KEY` | 生产环境务必替换为随机密钥：`python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `EMBEDDING_DIMENSIONS` | 须与 Milvus collection 维度一致，改动后需重建 collection |

### 4. 安装后端依赖并启动

```bash
# 基础依赖
uv sync

# 按需安装可选依赖
uv sync --extra dashscope     # DashScope Embedding / Rerank（默认方案）
uv sync --extra huggingface   # 如改用 HuggingFace 本地 Embedding
uv sync --extra langfuse      # 如需可观测性追踪

# 启动后端
uv run uvicorn app.main:app --reload --port 8000
```

- 交互式 API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/health>

> 依赖服务未就绪时后端只告警不中断启动，`/docs` 与 `/api/health` 始终可访问。

### 5. 启动前端

```bash
cd frontend-next
npm install
npm run dev
```

访问 <http://localhost:3001>。前端通过 `next.config.ts` 的 `rewrites` 将 `/backend/*` 代理到 `${BACKEND_BASE_URL}/api/*`，默认无需修改后端 CORS。详见 [frontend-next/README.md](frontend-next/README.md)。

### 6.（可选）接入 MCP 工具

复制配置模板并按需修改，重启后端即可让主管把「操作类」问题路由到 MCP 工具：

```bash
cp mcp.example.json mcp.json
```

`mcp.json` 的 `mcpServers` 支持本地进程（`command` / `args` / `transport=stdio`）与远程服务（`url` / `transport=sse|streamable_http`，可带 `headers`）。示例内置 `filesystem`（文件读写）与 `time`（日期时间 / 时区换算）两个官方 server。未配置 `mcp.json` 时 `mcp` 技能自动停用，不影响其它链路。可在前端「技能与工具」面板查看已连接的服务与工具，或访问 `GET /api/mcp/status`。

---

## 🔌 API 概览

### 认证

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/register` | 注册新用户并自动登录，返回 JWT |
| POST | `/api/auth/login` | 用户名密码登录，签发 JWT |
| GET | `/api/auth/me` | 获取当前登录用户（前端刷新恢复登录态） |

### 对话与知识库

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/chat` | 发送消息，返回 Agent 结构化响应（含路由与来源） |
| POST | `/api/chat/stream` | 流式对话（SSE），逐 token 推送 |
| POST | `/api/upload` | 上传知识库文件，落盘 + 解析 + 切片 + 向量化 |
| GET | `/api/history` | 获取指定会话历史消息 |
| GET | `/api/sessions` | 获取当前用户会话列表（最近活跃倒序） |
| DELETE | `/api/sessions/{session_id}` | 删除指定会话全部记录与 checkpoint 状态 |
| GET | `/api/files` | 获取已上传文件列表及处理状态 |
| DELETE | `/api/files/{file_id}` | 级联删除文件向量、元数据与磁盘文件 |
| GET | `/api/skills` | 列出注册表中已发现的可用技能（前端只读展示） |
| GET | `/api/mcp/status` | MCP 接入状态：已配置 server 与已加载工具 |
| GET | `/api/health` | PostgreSQL / Milvus 健康状态与统计 |

**SSE 事件类型**：`start` / `route` / `delta` / `sources` / `done` / `error`

除 `/api/auth/register`、`/api/auth/login`、`/api/health` 外，其余接口均需 `Authorization: Bearer <token>`。

---

## 🔍 RAG 检索链路

1. **解析**：MinerU API 将 PDF / 图片 / DOCX / PPTX / XLSX 转为高质量 Markdown，保留结构、公式与表格；`md/txt` 直接读取。
2. **切片**：两阶段策略——`MarkdownHeaderTextSplitter` 按 h1/h2/h3 保留层级，`RecursiveCharacterTextSplitter` 对超长节二次切分，每片前置标题路径作为上下文。
3. **向量化**：DashScope Embedding 按 `DASHSCOPE_BATCH_SIZE` 分批调用。
4. **入库**：稠密向量写入 Milvus，稀疏向量由 Milvus **BM25 Function** 在服务端自动从 `content` 生成；`user_id` 作为动态字段用于检索隔离。
5. **检索**：BM25 稀疏 + 稠密向量按 `MILVUS_SPARSE_WEIGHT / MILVUS_DENSE_WEIGHT` 加权融合，粗召回 `RERANK_RECALL` 条。
6. **重排序**：`qwen3-rerank` 精排取 `MILVUS_TOP_K`，失败时降级为原始排序。

---

## 🧩 技能系统（可插拔工作者）

系统的每个工作者都是一个「技能」，以独立文件放在 `app/skills/` 下，遵循统一契约：

1. 继承 `Skill`，提供 `metadata`（`SkillMetadata`：`name` 全局唯一，同时作为路由目标与图节点名；`description` 会写入主管的动态路由 Prompt，决定何时被选中；`label / icon / color / kind` 供前端展示）；
2. 实现 `async run(state)`，返回状态增量 `{"messages": [...], "sources": [...]}`；
3. 在模块末尾暴露 `skill = XxxSkill()` 实例。

启动时 `registry.discover()` 自动扫描并注册所有技能，`get_graph()` 据已启用技能动态构建 router 与工作者节点，`router_prompt()` 用各技能描述拼装主管系统 Prompt。因此**新增技能只需放入一个文件并重启，无需改动 `agent_graph.py` / `agents.py`**（二者不写死任何具体技能）。

当前内置 / 附带技能：

| 技能 | name | kind | 说明 |
| --- | --- | --- | --- |
| 知识库 | `rag` | builtin | 检索用户私有文档并标注 `[片段N]` 来源 |
| 联网搜索 | `search` | builtin | Tavily 实时检索并标注 `[N]` 引用 |
| 通用对话 | `chat` | builtin | 无需检索直接回答，同时作为路由兜底 |
| 天气查询 | `weather` | custom | Open-Meteo 实时天气（自定义技能示例） |
| 工具调用 | `mcp` | mcp | ReAct 循环调用外部 MCP 工具，未配置时自动停用 |

> `sources` 的 `kind` 有三类：`knowledge`（知识库片段）、`web`（联网结果）、`tool`（MCP / 天气等工具调用）。

---

## ⚙️ 主要配置项

完整配置见 [`.env.example`](.env.example) 与 [`app/config.py`](app/config.py)。常用项：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `CHAT_MODEL` | `deepseek-flash` | 对话模型（思考模式已在代码中关闭） |
| `TEMPERATURE` | `0.2` | 采样温度 |
| `EMBEDDING_MODEL` | `qwen3.7-text-embedding-flash` | 向量模型 |
| `EMBEDDING_DIMENSIONS` | `1024` | 向量维度，须与 collection 一致 |
| `RERANK_ENABLED` | `true` | 是否启用重排序 |
| `MILVUS_TOP_K` | `4` | 最终返回切片数 |
| `MILVUS_SPARSE_WEIGHT` / `MILVUS_DENSE_WEIGHT` | `0.3` / `0.7` | 混合检索权重（和建议为 1） |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1200` / `240` | 切片大小与重叠 |
| `HISTORY_WINDOW` | `20` | 无 checkpoint 时从 `chat_history` 灌入的历史条数（迁移 / 重建上下文） |
| `CHECKPOINT_BACKEND` | `postgres` | 会话状态存储：`postgres` 持久化到 PG（多实例共享）/ `memory` 进程内（单实例、重启丢失） |
| `MAX_UPLOAD_MB` | `20` | 单文件上传上限 |
| `MCP_ENABLED` | `true` | 是否启用 MCP 工具技能（还需配置 `mcp.json`） |
| `LANGFUSE_ENABLED` | `false` | 是否启用 Langfuse 追踪 |

---

## 📝 说明

- **上传格式白名单**：`.pdf .md .markdown .txt .docx .pptx .xlsx .png .jpg .jpeg`。
- **用户隔离**：知识库检索与会话历史均按 `user_id` 过滤，`thread_id` 拼接 `user_id` 防止跨用户上下文泄露。
- **会话状态持久化**：默认 `PostgresSaver` 把 LangGraph checkpoint 存入 PostgreSQL，多实例部署时同一会话可落到任意实例恢复上下文；checkpoint 表由启动时 `setup()` 幂等创建，删除会话会一并清除对应 checkpoint。checkpointer 使用独立的 psycopg 3 连接池（与 `pg_client` 的 psycopg2 池并存）。
- **维度变更**：修改 `EMBEDDING_DIMENSIONS` 后需删除并重建 Milvus collection。
- **Gradio 前端**：`frontend/gradio_app.py` 为轻量备用界面，主推 `frontend-next`。
- **MCP 配置**：`mcp.json` 已在 `.gitignore` 中忽略，仅 `mcp.example.json` 入库；工具列表进程内缓存，改动配置后需重启后端生效。

---

## 📄 License

本项目仅用于学习与研究目的。
