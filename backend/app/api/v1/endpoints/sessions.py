"""会话接口：历史列表 / 详情 / 断点续聊恢复（SSE，对齐 5.2 POST /sessions/{thread_id}/resume）"""
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.responses import fail, ok
from app.core.exceptions import ErrorCode
from app.mock_data import MESSAGES, SESSIONS
from app.schemas.requests import ResumeRequest
from app.services import memory

router = APIRouter()


@router.get("")
def list_sessions():
    return ok(SESSIONS)


@router.get("/{thread_id}")
def get_session(thread_id: str):
    """会话详情：优先真实短期记忆，回退 mock 种子"""
    if thread_id in MESSAGES:
        return ok({"thread_id": thread_id, "messages": MESSAGES[thread_id], "source": "store"})
    _summary, window = memory.get_context("default", "admin", thread_id)
    if window:
        return ok({
            "thread_id": thread_id,
            "messages": [{"id": f"m{i}", "role": m["role"], "content": m["content"], "attachments": []}
                         for i, m in enumerate(window, 1)],
            "source": "memory",
        })
    return fail(ErrorCode.NOT_FOUND, "会话不存在", 404)


@router.post("/{thread_id}/resume")
async def resume_session(thread_id: str, body: ResumeRequest):
    """断点续聊：同 thread_id 走 RAG 对话链路，短期记忆/任务状态自动延续（HITL 恢复共用通道）"""
    from app.api.v1.endpoints.chat import _rag_stream

    has_history = thread_id in MESSAGES or bool(memory.get_context("default", "admin", thread_id)[1])
    if not has_history:
        return fail(ErrorCode.NOT_FOUND, "会话不存在或已过期", 404)
    return StreamingResponse(
        _rag_stream(body.tenant_id, body.user_id, thread_id, body.content, None, None),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
