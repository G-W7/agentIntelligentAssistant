# Agent 智能助手 · Next.js 前端

React 19 + Next.js 16 实现的 Web 前端，用于替代 `frontend/gradio_app.py`。
纯展示层，只通过 HTTP 调用 FastAPI，不直接依赖后端内部模块。

## 功能

- **对话**：流式失败反馈、历史加载、会话切换 / 新建、Markdown 渲染。
- **Agent 路由可视化**：每条回答标注 `知识库 / 联网搜索 / 通用对话` 路由与判断依据。
- **参考来源**：知识库片段显示文件名、页码、相关度与内容摘要；联网结果可点击跳转。
- **知识库**：拖拽 / 多文件上传、逐文件进度与结果、文件列表、状态徽章、复制文件 ID、删除确认。
- **服务状态**：PostgreSQL / Milvus 健康检查，向量数与文件数统计，30 秒自动刷新。
- **体验**：深色模式、响应式布局、中文输入法友好的 Enter 发送、自动滚动。

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

访问 <http://localhost:3001>。

生产构建：

```bash
npm run build
npm start
```

## 配置

复制 `.env.example` 为 `.env.local`：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `BACKEND_BASE_URL` | `http://127.0.0.1:8000` | Next.js 服务端代理目标，浏览器不感知 |
| `NEXT_PUBLIC_API_BASE_URL` | 空 | 可选。设置后浏览器直连后端，需要后端 CORS 放行 |

浏览器请求 `/backend/*`，由 `next.config.ts` 的 `rewrites` 转发到
`${BACKEND_BASE_URL}/api/*`，因此默认无需修改后端 `CORS_ORIGINS`。

## 目录

```
src/
├── app/                  # App Router：layout / page / QueryClient Provider
├── components/
│   ├── chat/             # 对话、Markdown、路由徽章、来源、会话栏
│   ├── knowledge/        # 上传、文件列表、删除确认
│   ├── ui/               # shadcn / Base UI 组件
│   ├── app-header.tsx
│   ├── assistant-app.tsx # 页面组合
│   └── service-status.tsx
├── hooks/                # TanStack Query 查询、useChat、useMounted
├── lib/                  # API 客户端、类型、格式化、常量
└── stores/               # Zustand 会话状态（localStorage 持久化）
```

## 说明

- 后端 `/api/chat` 为非流式接口，前端以“思考中”气泡反馈等待状态。
- 会话 ID 持久化在 `localStorage`；不同会话的历史记录由后端 PostgreSQL 保存。
- 上传支持格式与大小限制与 `app/config.py` 保持一致（默认单文件 20 MB）。
