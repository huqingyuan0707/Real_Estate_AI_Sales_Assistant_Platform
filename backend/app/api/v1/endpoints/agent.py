"""Agent 对外端点（文档 5.2 风格）：chat / stream / approvals / tasks / eval。"""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.exceptions import ErrorCode
from app.core.rbac import get_current_user
from app.core.dependencies import get_agent_service
from app.core.responses import fail, ok
from app.modules.agent.policy.approval import ApprovalService
from app.modules.agent.schemas import ChatRequest

router = APIRouter(tags=["agent-engine"])
_approvals = ApprovalService()


class ApproveBody(BaseModel):
    modified_args: dict | None = None


class EvalBody(BaseModel):
    agent_version: str = "dev"


@router.post("/agent/chat")
async def agent_chat(payload: ChatRequest, service=Depends(get_agent_service),
                     user=Depends(get_current_user)):
    return ok(await service.chat(payload, user))


@router.post("/agent/chat/stream")
async def agent_chat_stream(payload: ChatRequest, service=Depends(get_agent_service),
                            user=Depends(get_current_user)):
    async def gen():
        async for ev in service.stream_chat(payload, user):
            yield f"data: {ev.model_dump_json()}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/approvals/{approval_id}/approve")
async def approve(approval_id: str, body: ApproveBody,
                  user=Depends(get_current_user)):
    try:
        return ok(await _approvals.approve(approval_id, user, body.modified_args))
    except KeyError:
        return fail(ErrorCode.NOT_FOUND, "审批单不存在", 404)
    except PermissionError as e:
        return fail(ErrorCode.FORBIDDEN, str(e) or "无审批权限", 403)


@router.post("/approvals/{approval_id}/reject")
async def reject(approval_id: str, user=Depends(get_current_user)):
    try:
        return ok(await _approvals.reject(approval_id, user))
    except KeyError:
        return fail(ErrorCode.NOT_FOUND, "审批单不存在", 404)


@router.get("/tasks/{task_id}")
async def task_status(task_id: str, user=Depends(get_current_user)):
    """长任务状态查询：以任务中心真实存储为准（engine 内存仅为 Celery 缺失时的降级）。"""
    try:
        from app.services import task_center

        task = task_center.get(task_id)
        if task:
            return ok(task)
    except Exception:
        pass
    try:
        from app.workers.tasks import get_task

        task = get_task(task_id)
    except Exception:
        task = None
    if not task:
        return ok({"status": "not_found"}, msg="任务不存在")
    return ok(task)


@router.post("/eval/run")
async def eval_run(body: EvalBody, user=Depends(get_current_user)):
    from app.modules.agent.evaluation.service import EvaluationService

    return ok(await EvaluationService().run(agent_version=body.agent_version))
