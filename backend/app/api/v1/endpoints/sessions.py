"""会话接口：历史列表 / 详情 / 断点续聊恢复（SSE，对齐 5.2 POST /sessions/{thread_id}/resume）

读写键必须与 /chat 写入一致：(tenant, Token 真实用户名, thread_id)。
历史 bug：读取端硬编码 "admin"，而 /chat 按 Token 用户写入，导致历史永远查不到。
"""
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.responses import fail, ok
from app.core.exceptions import ErrorCode
from app.core.rbac import get_current_user
from app.mock_data import MESSAGES, SESSIONS
from app.schemas.requests import ResumeRequest
from app.services import governance, memory

router = APIRouter()


def _me(user: dict) -> str:
    """当前登录用户名（与 /chat 写入记忆的 user_id 口径一致）"""
    return user.get("username") or "anonymous"


def _fmt_time(ts: str) -> tuple[str, str]:
    """ISO 时间 → (分组, 展示时间)：今天 HH:MM / 昨天 HH:MM / 更早 MM-DD"""
    try:
        local = datetime.fromisoformat(ts).astimezone()
    except (TypeError, ValueError):
        return "更早", ""
    days = (datetime.now().date() - local.date()).days
    if days <= 0:
        return "今天", local.strftime("%H:%M")
    if days == 1:
        return "昨天", local.strftime("%H:%M")
    return "更早", local.strftime("%m-%d")


@router.get("")
def list_sessions(user: dict = Depends(get_current_user)):
    """历史会话列表：读取当前登录用户的真实短期记忆，键口径与 /chat 写入端一致。

    历史 bug：此处曾硬编码返回 mock 常量 SESSIONS（且未鉴权），
    真实会话永远不出现在左侧列表 → 表现为"历史对话没有保存记录"。
    """
    threads = memory.list_threads("default", _me(user))
    if not threads:
        # 演示兜底：尚无任何真实会话时给出种子数据，避免首启空列表
        return ok(SESSIONS)
    data = []
    for t in threads:
        group, time_text = _fmt_time(t["updated_at"])
        data.append({**t, "group": group, "time": time_text})
    return ok(data)


@router.get("/{thread_id}")
def get_session(thread_id: str, user: dict = Depends(get_current_user)):
    """会话详情：优先真实短期记忆，回退 mock 种子。

    顺序不能反：列表标题取自真实记忆，若详情优先命中 mock，
    会出现"左侧标题与右侧内容不符"。
    """
    _summary, window = memory.get_context("default", _me(user), thread_id)
    if window:
        return ok({
            "thread_id": thread_id,
            "messages": [{"id": f"m{i}", "role": m["role"], "content": m["content"], "attachments": []}
                         for i, m in enumerate(window, 1)],
            "source": "memory",
        })
    if thread_id in MESSAGES:
        return ok({"thread_id": thread_id, "messages": MESSAGES[thread_id], "source": "store"})
    return fail(ErrorCode.NOT_FOUND, "会话不存在", 404)


@router.delete("/{thread_id}")
def delete_session(thread_id: str, user: dict = Depends(get_current_user)):
    """删除会话的短期记忆。历史 bug：前端只删本地、后端无对应端点，刷新后会话"复活"。"""
    if not memory.clear_short("default", _me(user), thread_id):
        return fail(ErrorCode.NOT_FOUND, "会话不存在", 404)
    return ok({"thread_id": thread_id, "deleted": True})


@router.post("/{thread_id}/resume")
async def resume_session(thread_id: str, body: ResumeRequest, user: dict = Depends(get_current_user)):
    """断点续聊：同 thread_id 走 RAG 对话链路，短期记忆/任务状态自动延续（HITL 恢复共用通道）"""
    from app.api.v1.endpoints.chat import _rag_stream

    has_history = thread_id in MESSAGES or bool(memory.get_context("default", _me(user), thread_id)[1])
    if not has_history:
        return fail(ErrorCode.NOT_FOUND, "会话不存在或已过期", 404)
    # ctx 必须是由 access_context 构造的字典（含租户/角色/可见密级），
    # 历史 bug 曾把 tenant_id/user_id 两个字符串直接传给 _rag_stream 导致 TypeError。
    ctx = governance.access_context(body.tenant_id)
    return StreamingResponse(
        _rag_stream(ctx, thread_id, body.content, None, None),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
