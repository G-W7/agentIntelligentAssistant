# Agent 智能助手 · Next.js 前端

React 19 + Next.js 16 实现的 Web 前端，用于替代 `frontend/gradio_app.py`。
纯展示层，只通过 HTTP 调用 FastAPI，不直接依赖后端内部模块。

## 技术栈

| 类别 | 选型 |
| --- | --- |
| 框架 | Next.js 16（App Router + Turbopack）、React 19、TypeScript |
| 样式 / UI | Tailwind CSS 4、shadcn 风格组件（基于 `@base-ui/react`）、`lucide-react` 图标 |
| 数据层 | TanStack Query（服务端状态 + 缓存）、Zustand（会话 / 登录态，localStorage 持久化） |
| 其他 | `react-markdown` + `remark-gfm`（消息渲染）、`react-hook-form` + `zod`（表单校验） |

## 功能

- **登录鉴权**：注册 / 登录获取 JWT，令牌持久化并在所有请求自动注入 `Authorization` 头；收到 401 自动清除登录态回到登录页。
- **流式对话**：基于 SSE（`POST /api/chat/stream`）逐字增量渲染，支持中途取消；失败时保留已收到的部分回答并提示。
- **Agent 路由可视化**：每条回答标注 `知识库(rag) / 联网搜索(search) / 通用对话(chat)` 路由与判断依据。
- **参考来源**：知识库片段显示文件名、页码、相关度与内容摘要；联网结果可点击跳转。
- **会话管理**：会话侧边栏支持切换 / 新建 / 删除会话，展示消息数与最后活动时间；当前会话 ID 持久化，刷新后继续原会话。
- **知识库**：拖拽 / 多文件上传、逐文件进度与结果、文件列表、状态徽章、复制文件 ID、删除确认。
- **服务状态**：PostgreSQL / Milvus 健康检查，向量数与文件数统计，30 秒自动刷新。
- **体验**：深色模式、响应式布局、中文输入法友好的 Enter 发送、自动滚动、历史消息 Markdown 渲染。

## 启动

后端先运行在 `http://127.0.0.1:8000`（项目根目录）：

```bash
uv run uvicorn app.main:app --reload --port 8000
```

再启动前端：

```bash
cd frontend-next
npm install
npm run dev
```

访问 <http://localhost:3001>（`dev` / `start` 均固定使用 3001 端口）。

常用脚本：

| 命令 | 说明 |
| --- | --- |
| `npm run dev` | 开发模式（Turbopack，端口 3001） |
| `npm run build` | 生产构建 |
| `npm start` | 启动生产构建（端口 3001） |
| `npm run lint` | ESLint 检查 |

## 配置

复制 `.env.example` 为 `.env.local`：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `BACKEND_BASE_URL` | `http://127.0.0.1:8000` | Next.js 服务端代理目标，浏览器不感知 |
| `NEXT_PUBLIC_API_BASE_URL` | 空 | 可选。设置后浏览器直连后端，需要后端 CORS 放行 |

浏览器请求 `/backend/*`，由 `next.config.ts` 的 `rewrites` 转发到
`${BACKEND_BASE_URL}/api/*`，因此默认无需修改后端 `CORS_ORIGINS`。

## 后端接口

前端用到的接口一览（均经 `/backend` 代理，需携带 `Authorization: Bearer <token>`，`/auth/*` 除外）：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/auth/register` / `/auth/login` | 注册 / 登录，返回令牌与用户信息 |
| GET | `/auth/me` | 获取当前用户 |
| POST | `/chat/stream` | 流式对话（SSE） |
| POST | `/chat` | 非流式对话（备用） |
| GET | `/history?session_id=&limit=` | 拉取会话历史消息 |
| GET | `/sessions?limit=` | 会话列表 |
| DELETE | `/sessions/{session_id}` | 删除会话及其消息 |
| POST | `/upload` | 上传知识库文件（multipart） |
| GET | `/files` | 文件列表 |
| DELETE | `/files/{file_id}` | 删除文件及对应向量 |
| GET | `/health` | 服务健康状态 |

### SSE 事件契约

`/chat/stream` 依次推送以下事件（与 `src/lib/types.ts` 的 `ChatStreamEvent` 一致）：

| 事件 | 说明 |
| --- | --- |
| `start` | 流开始，携带 `session_id` |
| `route` | 路由结果与判断依据 |
| `delta` | 回答内容增量片段 |
| `sources` | 参考来源列表 |
| `done` | 完整回答 + 路由 + 来源（终态） |
| `error` | 错误信息，前端中断并提示 |

## 目录

```
src/
├── app/                  # App Router：layout / page / QueryClient Provider
├── components/
│   ├── auth/             # 登录 / 注册界面
│   ├── chat/             # 对话、Markdown、路由徽章、来源、会话栏与侧边栏
│   ├── knowledge/        # 上传、文件列表、删除确认
│   ├── ui/               # shadcn / Base UI 组件
│   ├── app-header.tsx
│   ├── assistant-app.tsx # 页面组合
│   ├── service-status.tsx
│   └── theme-toggle.tsx
├── hooks/                # TanStack Query 查询、useChat（SSE 流式）、useMounted
├── lib/                  # API 客户端（含 SSE 解析）、类型契约、常量、格式化
└── stores/               # Zustand：会话状态 + 登录态（均 localStorage 持久化）
```

## 说明

- 登录态（`agent-assistant-auth`）与当前会话 ID（`agent-assistant-session`）分别持久化在 `localStorage`；历史消息由后端 PostgreSQL 保存。
- 上传格式与大小限制与后端 `app/config.py` 对齐：`pdf / md / txt / docx / pptx / xlsx / png / jpg`，默认单文件 20 MB（前端在上传前即时校验）。
- 消息长度上限 8000 字符，会话 ID 上限 100 字符（`src/lib/constants.ts`）。
- 各接口均设置了超时：健康检查 15s、常规查询 30s、非流式对话 300s、上传 600s、删除文件 120s。
