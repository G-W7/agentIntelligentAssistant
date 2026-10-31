import asyncio
import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.config import get_settings
from app.core.agent_graph import get_graph
from app.db import pg_client
from frontend.gradio_app import session_id

pg_client.init_db()
_ROLE_CLASSES = {"user": HumanMessage, "assistant": AIMessage}
session_id = "default"
rows = pg_client.list_messages(session_id, limit=get_settings().history_window)
print(rows)
messages: list[BaseMessage] = []
for row in rows:
    message_class = _ROLE_CLASSES.get(row["role"])
    print(message_class)
