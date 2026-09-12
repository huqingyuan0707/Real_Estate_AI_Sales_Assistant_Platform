"""Agent 请求/响应 Schema（Pydantic v2） thin DTO，业务逻辑不得下沉到此层。"""
from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)
    session_id: str = "default"
    stream: bool = False
    idempotency_key: str | None = None


class ChatResponse(BaseModel):
    answer: str
    trace_id: str


class StreamEvent(BaseModel):
    """统一流式事件协议：text/tool_call/tool_result/approval/error/done。"""

    type: Literal["text", "tool_call", "tool_result", "approval", "error", "done"]
    content: str | None = None
    name: str | None = None
    args: dict[str, Any] | None = None
    result: Any | None = None
    action: str | None = None
    code: str | None = None
    message: str | None = None
    trace_id: str | None = None
