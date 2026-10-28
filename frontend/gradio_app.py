"""Gradio 前端（设计文档 3.1 前端展示层）。

纯展示层：只通过 HTTP 调用 FastAPI，不直接依赖 app 包内部模块，
因此可以独立进程运行，也便于将来替换为 React/Vue。

启动：python frontend/gradio_app.py
"""

import os
from pathlib import Path
from urllib.parse import quote

import gradio as gr
import httpx
from dotenv import load_dotenv

load_dotenv()

BACKEND = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

FILE_HEADERS = ["文件名", "类型", "大小", "状态", "文件 ID"]


def _detail(response: httpx.Response) -> str:
    try:
        return str(response.json().get("detail", response.text))
    except ValueError:
        return response.text


def _human_size(size: int | None) -> str:
    if size is None:
        return "-"
    value = float(size)
    for unit in ("B", "KB", "MB"):
        if value < 1024:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _safe_url(url: str) -> str:
    """搜索结果来自外部，只放行 http/https，避免 markdown 注入 javascript: 链接。"""
    return url if url.startswith(("http://", "https://")) else ""


def _render_sources(sources: list[dict]) -> str:
    lines = []
    for source in sources:
        if source.get("kind") == "knowledge":
            location = f" 第 {source['page']} 页" if source.get("page") else ""
            lines.append(
                f"- 📄 `{source.get('file_id', '')[:8]}`{location} · "
                f"相关度 {source.get('score', 0):.3f}"
            )
        else:
            title = (source.get("title") or "").replace("[", "").replace("]", "")
            url = _safe_url(source.get("url") or "")
            lines.append(f"- 🔗 {title}" + (f" — <{url}>" if url else ""))
    return "\n".join(lines)


def _render_answer(data: dict) -> str:
    answer = data.get("answer", "")
    sources = data.get("sources") or []
    if sources:
        answer += "\n\n---\n**参考来源**\n" + _render_sources(sources)
    return answer


def respond(message: str, history: list[dict], session_id: str):
    if not message.strip():
        raise gr.Error("请输入消息内容")

    yield history + [{"role": "user", "content": message}], "", "⏳ Agent 处理中…"

    try:
        response = httpx.post(
            f"{BACKEND}/api/chat",
            json={"message": message, "session_id": session_id},
            timeout=300,
        )
        if response.status_code != 200:
            raise gr.Error(f"后端返回 {response.status_code}：{_detail(response)}")
    except httpx.HTTPError as exc:
        raise gr.Error(f"无法连接后端 {BACKEND}：{exc}") from exc

    data = response.json()
    history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": _render_answer(data)},
    ]
    status = f"🧭 路由：**{data.get('route')}** — {data.get('route_reason', '')}"
    yield history, "", status


def load_history(session_id: str) -> list[dict]:
    try:
        response = httpx.get(
            f"{BACKEND}/api/history", params={"session_id": session_id}, timeout=30
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        gr.Warning(f"加载历史失败：{exc}")
        return []
    return [
        {"role": item["role"], "content": item["content"]} for item in response.json()
    ]


def load_files() -> list[list[str]]:
    try:
        response = httpx.get(f"{BACKEND}/api/files", timeout=30)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        gr.Warning(f"获取文件列表失败：{exc}")
        return []
    return [
        [
            item["filename"],
            item.get("file_type") or "-",
            _human_size(item.get("file_size")),
            item.get("status") or "-",
            item["id"],
        ]
        for item in response.json()
    ]


def upload_files(files: list[str] | None) -> tuple[str, list[list[str]]]:
    if not files:
        raise gr.Error("请先选择要上传的文件")

    lines = []
    for raw_path in files:
        path = Path(raw_path)
        try:
            response = httpx.post(
                f"{BACKEND}/api/upload",
                files={"file": (path.name, path.read_bytes())},
                timeout=600,
            )
        except httpx.HTTPError as exc:
            lines.append(f"❌ `{path.name}` → {exc}")
            continue

        if response.status_code == 200:
            data = response.json()
            lines.append(
                f"✅ `{path.name}` → {data['chunk_count']} 个切片，"
                f"状态 {data['file']['status']}"
            )
        else:
            lines.append(f"❌ `{path.name}` → {response.status_code} {_detail(response)}")

    return "\n\n".join(lines), load_files()


def delete_file(file_id: str) -> tuple[str, list[list[str]]]:
    file_id = file_id.strip()
    if not file_id:
        raise gr.Error("请填写要删除的文件 ID")

    try:
        response = httpx.delete(f"{BACKEND}/api/files/{quote(file_id)}", timeout=120)
        if response.status_code == 404:
            raise gr.Error(f"文件不存在：{file_id}")
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise gr.Error(f"删除失败：{exc}") from exc

    data = response.json()
    return f"🗑️ 已删除 `{file_id}`，清理 {data['deleted_vectors']} 条向量", load_files()


def check_health() -> dict:
    try:
        response = httpx.get(f"{BACKEND}/api/health", timeout=15)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as exc:
        return {"status": "unreachable", "backend": BACKEND, "error": str(exc)}


with gr.Blocks(title="Agent 智能助手") as demo:
    gr.Markdown(
        "# 🤖 Agent 智能助手\n"
        "多 Agent 协作（主管-工作者）· 本地知识库 RAG · Tavily 联网搜索"
    )

    with gr.Row():
        with gr.Column(scale=3):
            session_id = gr.Textbox(label="会话 ID", value="default")
            chatbot = gr.Chatbot(label="对话", height=520)
            with gr.Row():
                message = gr.Textbox(
                    label="消息", scale=5, placeholder="输入问题后回车发送…"
                )
                send = gr.Button("发送", variant="primary", scale=1)
            status = gr.Markdown()

        with gr.Column(scale=2):
            health = gr.JSON(label="服务状态")
            refresh_health = gr.Button("刷新状态")

            gr.Markdown("### 📚 知识库")
            upload = gr.File(
                label="选择文档（PDF / Markdown / TXT）", file_count="multiple"
            )
            upload_btn = gr.Button("上传并向量化", variant="primary")
            upload_result = gr.Markdown()
            files_table = gr.Dataframe(headers=FILE_HEADERS, label="已上传文件")
            with gr.Row():
                refresh_files = gr.Button("刷新列表")
            delete_id = gr.Textbox(label="要删除的文件 ID")
            delete_btn = gr.Button("删除文件及向量")

    send.click(respond, [message, chatbot, session_id], [chatbot, message, status])
    message.submit(respond, [message, chatbot, session_id], [chatbot, message, status])
    session_id.change(load_history, [session_id], [chatbot])

    upload_btn.click(upload_files, [upload], [upload_result, files_table])
    refresh_files.click(load_files, None, [files_table])
    delete_btn.click(delete_file, [delete_id], [upload_result, files_table])
    refresh_health.click(check_health, None, [health])

    demo.load(check_health, None, [health]).then(load_files, None, [files_table])


if __name__ == "__main__":
    print(f"后端地址：{BACKEND}")
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        inbrowser=True,
        theme=gr.themes.Soft(),
    )
