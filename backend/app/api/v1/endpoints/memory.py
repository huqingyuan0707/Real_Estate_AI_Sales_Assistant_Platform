"""记忆管理接口

短期记忆：查看 / 清空（当前会话窗口消息、滚动摘要、任务状态）
长期记忆：查看 / 新增 / 修改 / 删除 / 授权确认（租户+用户隔离，敏感信息强制过期）
"""
from fastapi import APIRouter, Depends

from app.core.exceptions import ErrorCode
from app.core.rbac import get_current_user
from app.core.responses import fail, ok
from app.schemas.requests import MemoryCreateRequest, MemoryUpdateRequest
from app.services import memory

router = APIRouter()


def _resolve_uid(user_id: str | None, user: dict) -> str:
    """记忆读写用户键：显式传非默认 user_id 则尊重（测试/管理工具），
    否则一律用 Token 真实用户——必须与 /chat 写入键一致，否则历史查不到。"""
    if user_id and user_id != "admin":
        return user_id
    return user.get("username") or "admin"


# ---------------- 短期记忆 ----------------


@router.get("/short/{thread_id}")
async def get_short_memory(thread_id: str, tenant_id: str = "default", user_id: str | None = None,
                            user: dict = Depends(get_current_user)):
    """查看当前会话的短期记忆：滚动摘要 + 窗口内消息 + 任务状态"""
    summary, messages = memory.get_context(tenant_id, _resolve_uid(user_id, user), thread_id)
    tokens = memory.est_tokens(summary) + sum(memory.est_tokens(m["content"]) for m in messages)
    return ok({
        "thread_id": thread_id,
        "summary": summary,
        "messages": messages,
        "message_count": len(messages),
        "est_tokens": tokens,
        "token_budget": 2000,
        "window": 12,
    })


@router.delete("/short/{thread_id}")
async def clear_short_memory(thread_id: str, tenant_id: str = "default", user_id: str | None = None,
                              user: dict = Depends(get_current_user)):
    """清空当前会话的短期记忆（开始新话题时使用）"""
    removed = memory.clear_short(tenant_id, _resolve_uid(user_id, user), thread_id)
    return ok({"cleared": removed})


@router.get("/stats")
async def memory_stats(tenant_id: str = "default", user_id: str | None = None,
                       user: dict = Depends(get_current_user)):
    """记忆总览：短期会话数 + 长期记忆统计"""
    return ok({
        "short": memory.short_stats(),
        "long": memory.long_stats(tenant_id, _resolve_uid(user_id, user)),
    })


# ---------------- 长期记忆 ----------------


@router.get("/long")
async def list_long_memory(tenant_id: str = "default", user_id: str | None = None,
                           user: dict = Depends(get_current_user)):
    """查看本用户的长期记忆（含待授权条目）"""
    return ok({"items": memory.list_long(tenant_id, _resolve_uid(user_id, user))})


@router.post("/long")
async def create_long_memory(body: MemoryCreateRequest, user: dict = Depends(get_current_user)):
    """写入长期记忆：
    - authorized=False → pending（待用户确认，不注入对话）
    - 敏感信息（手机号/身份证/银行卡）必须设置过期时间
    """
    try:
        entry = memory.add_long(
            body.tenant_id, _resolve_uid(body.user_id, user), body.content,
            category=body.category, authorized=body.authorized, expires_days=body.expires_days,
        )
    except memory.MemoryDenied as e:
        return fail(ErrorCode.PARAM_INVALID, str(e))
    return ok(entry, msg="已写入长期记忆（pending，待授权）" if not entry["authorized"] else "success")


@router.put("/long/{memory_id}")
async def update_long_memory(memory_id: str, body: MemoryUpdateRequest,
                             user: dict = Depends(get_current_user)):
    """修改长期记忆内容/分类/过期时间，或进行授权确认"""
    entry = memory.update_long(
        body.tenant_id, _resolve_uid(body.user_id, user), memory_id,
        content=body.content, category=body.category,
        authorized=body.authorized, expires_days=body.expires_days,
    )
    if entry is None:
        return fail(ErrorCode.NOT_FOUND, "记忆条目不存在")
    return ok(entry)


@router.delete("/long/{memory_id}")
async def delete_long_memory(memory_id: str, tenant_id: str = "default", user_id: str | None = None,
                             user: dict = Depends(get_current_user)):
    if not memory.delete_long(tenant_id, _resolve_uid(user_id, user), memory_id):
        return fail(ErrorCode.NOT_FOUND, "记忆条目不存在")
    return ok({"deleted": memory_id})
