"""任务中心接口（对齐 5.2 /task/{task_id}/status|stream|DELETE 与 11.1 异步任务规范）

- GET  /tasks                     任务列表（真实任务 + 演示种子合并）
- GET  /tasks/{task_id}/status    统一任务状态查询（渲染任务同样纳入）
- GET  /tasks/{task_id}/stream    SSE 完成推送（替代被动轮询，见 11.1.5）
- DELETE /tasks/{task_id}         取消排队/执行中的任务
- POST /tasks/{task_id}/cancel    取消（前端兼容别名）
- POST /tasks/{task_id}/retry     按原参数重新提交
"""
import asyncio
import json
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.responses import fail, ok
from app.core.exceptions import ErrorCode
from app.mock_data import TASKS
from app.services import task_center
from app.services import render as render_service

router = APIRouter()

_STATUS_OUT = {"pending": "queued", "running": "running", "completed": "done",
               "failed": "failed", "cancelled": "cancelled"}


def _fmt_tc(rec: dict) -> dict:
    return {
        "id": rec["task_id"],
        "task_type": rec["task_type"],
        "name": rec["name"],
        "submitted_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(rec["created_at"])),
        "progress": rec["progress"],
        "status": _STATUS_OUT[rec["status"]],
        "phase": rec["phase"],
        "result": rec["result"],
        "error": rec["error"],
        "real": True,
    }


def _fmt_render(t) -> dict:
    return {
        "id": t.task_id,
        "task_type": "effect_render",
        "name": f"效果图渲染 · {t.resolution.upper()}",
        "submitted_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(t.created_at)),
        "progress": t.progress,
        "status": t.status,
        "phase": t.phase,
        "result": {"image_url": t.image_url} if t.image_url else None,
        "error": t.phase if t.status == "failed" else None,
        "real": True,
    }


def _lookup(task_id: str) -> dict | None:
    """统一查询：任务中心注册表优先，其次渲染任务表"""
    rec = task_center.get(task_id)
    if rec:
        return _fmt_tc(rec)
    t = render_service.get_task(task_id)
    if t:
        return _fmt_render(t)
    return None


def _sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


@router.get("")
def list_tasks():
    """真实任务（进行中优先）+ 演示种子合并展示"""
    real = [
        *[_fmt_tc(r) for r in task_center.list_all()],
        *[_fmt_render(t) for t in render_service.get_all_tasks()
          if t.status in ("queued", "running")],
    ]
    return ok([*real, *TASKS])


@router.get("/{task_id}/status")
def task_status(task_id: str):
    st = _lookup(task_id)
    if st is None:
        if task_center.is_evicted(task_id):
            return fail(ErrorCode.TASK_EXPIRED, "任务已过期（结果被清理），请重新发起", 410)
        return fail(ErrorCode.NOT_FOUND, "任务不存在", 404)
    return ok(st)


@router.get("/{task_id}/stream")
async def task_stream(task_id: str):
    """SSE 任务完成推送：进度变化推 progress，终态推 complete 并关闭（11.1.5）"""
    if _lookup(task_id) is None:
        code = ErrorCode.TASK_EXPIRED if task_center.is_evicted(task_id) else ErrorCode.NOT_FOUND
        return fail(code, "任务不存在或已过期" if code == ErrorCode.TASK_EXPIRED else "任务不存在",
                    410 if code == ErrorCode.TASK_EXPIRED else 404)

    async def _gen():
        last: tuple | None = None
        deadline = time.time() + 300  # 最长挂 5 分钟，防止连接悬挂
        while time.time() < deadline:
            st = _lookup(task_id)
            if st is None:
                yield _sse("error", json.dumps({"code": ErrorCode.TASK_EXPIRED, "msg": "任务已过期"}, ensure_ascii=False))
                return
            key = (st["status"], st["progress"], st["phase"])
            if key != last:
                last = key
                yield _sse("progress", json.dumps(st, ensure_ascii=False))
            if st["status"] in ("done", "failed", "cancelled"):
                yield _sse("complete", json.dumps(st, ensure_ascii=False))
                return
            await asyncio.sleep(0.5)
        yield _sse("error", json.dumps({"code": ErrorCode.NETWORK_UNSTABLE, "msg": "推送超时，请改用轮询"}, ensure_ascii=False))

    return StreamingResponse(_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.delete("/{task_id}")
def delete_task(task_id: str):
    """取消排队/执行中的异步任务"""
    if task_center.cancel(task_id) or render_service.cancel_task(task_id):
        return ok({"task_id": task_id, "status": "cancelled"}, "任务已取消")
    if _lookup(task_id) is None:
        return fail(ErrorCode.NOT_FOUND, "任务不存在", 404)
    return fail(ErrorCode.TASK_CONFLICT, "任务已结束，无法取消", 409)


@router.post("/{task_id}/cancel")
def cancel_task(task_id: str):
    return delete_task(task_id)


@router.post("/{task_id}/retry")
async def retry_task(task_id: str):
    """按原参数重新提交（真实任务走 task_center 重跑；演示任务保持原行为）"""
    new_rec = task_center.retry(task_id)
    if new_rec:
        return ok(_fmt_tc(new_rec), "已按原参数重新提交")
    if _lookup(task_id) is not None:
        return ok({"task_id": f"tk-{task_id}-retry", "status": "queued", "from": task_id},
                  "已按原参数重新提交（演示）")
    return fail(ErrorCode.NOT_FOUND, "任务不存在", 404)
