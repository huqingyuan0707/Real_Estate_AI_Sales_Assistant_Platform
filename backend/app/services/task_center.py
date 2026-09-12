"""统一异步任务中心（对齐技术方案 11.1 async_tasks 表语义的进程内实现）

职责：所有长时操作（批量导入 / 效果图渲染 / 户型深度解析…）统一注册为任务，
提供 状态查询（status）、进度上报（progress/phase）、取消（cancel）、
SSE 完成推送（配合 endpoints/tasks.py 的 /stream）。

生产环境可平滑替换为 Celery+Redis Worker（task_type/status/progress/payload/result
字段与 async_tasks 表一一对应），本模块接口契约保持不变。
"""
import asyncio
import time
import uuid

# 状态机：pending → running → completed / failed / cancelled
MAX_RECORDS = 200          # 注册表上限，超出淘汰最旧终态任务
_tasks: dict[str, dict] = {}
_asyncio_tasks: dict[str, asyncio.Task] = {}
_evicted_ids: set[str] = set()   # 被 cleanup 淘汰的任务 id → 查询时返回 4002 任务已过期


def _now() -> float:
    return time.time()


def create(task_type: str, name: str, payload: dict | None = None) -> dict:
    """注册任务（pending），返回任务记录"""
    task_id = uuid.uuid4().hex
    rec = {
        "task_id": task_id,
        "task_type": task_type,        # batch_import / effect_render / deep_parse
        "name": name,
        "status": "pending",
        "progress": 0,
        "phase": "排队中",
        "payload": payload or {},
        "result": None,
        "error": None,
        "created_at": _now(),
        "updated_at": _now(),
        "completed_at": None,
    }
    _tasks[task_id] = rec
    _evict()
    return rec


_factories: dict[str, callable] = {}   # task_id -> 业务协程工厂（重试时按原参数重跑）


def attach(task_id: str, factory) -> None:
    """挂载业务协程工厂（零参，返回 coroutine；进程内 Worker 自动维护状态机）"""
    _factories[task_id] = factory
    _asyncio_tasks[task_id] = asyncio.create_task(_run(task_id, factory()))


def retry(task_id: str) -> dict | None:
    """按原 payload 重新提交任务，返回新任务记录"""
    old = _tasks.get(task_id)
    if not old:
        return None
    factory = _factories.get(task_id)
    if not factory:
        return None
    rec = create(old["task_type"], old["name"], old["payload"])
    attach(rec["task_id"], factory)
    return rec


async def _run(task_id: str, coro) -> None:
    rec = _tasks.get(task_id)
    if not rec:
        return
    rec.update(status="running", phase="执行中", updated_at=_now())
    try:
        result = await coro
        rec.update(status="completed", result=result, progress=100,
                   phase="已完成", completed_at=_now(), updated_at=_now())
    except asyncio.CancelledError:
        rec.update(status="cancelled", phase="已取消", completed_at=_now(), updated_at=_now())
    except Exception as e:  # 业务异常 → failed（不阻塞事件循环）
        rec.update(status="failed", error=str(e)[:300], phase="执行失败",
                   completed_at=_now(), updated_at=_now())
    finally:
        _asyncio_tasks.pop(task_id, None)
        # failed/cancelled 保留工厂供 retry 重跑；completed 清除释放闭包内存
        if rec["status"] == "completed":
            _factories.pop(task_id, None)


def set_progress(task_id: str, progress: int, phase: str = "") -> None:
    rec = _tasks.get(task_id)
    if rec and rec["status"] == "running":
        rec["progress"] = max(rec["progress"], min(99, int(progress)))
        if phase:
            rec["phase"] = phase
        rec["updated_at"] = _now()


def get(task_id: str) -> dict | None:
    return _tasks.get(task_id)


def cancel(task_id: str) -> bool:
    """取消排队/执行中的任务；终态任务返回 False"""
    rec = _tasks.get(task_id)
    if not rec or rec["status"] in ("completed", "failed", "cancelled"):
        return False
    t = _asyncio_tasks.pop(task_id, None)
    if t and not t.done():
        t.cancel()
    rec.update(status="cancelled", phase="已取消", completed_at=_now(), updated_at=_now())
    return True


def list_all() -> list[dict]:
    return sorted(_tasks.values(), key=lambda r: r["created_at"], reverse=True)


def is_evicted(task_id: str) -> bool:
    """任务曾经存在但记录已被清理 → 4002 任务已过期"""
    return task_id in _evicted_ids


def _evict() -> None:
    if len(_tasks) <= MAX_RECORDS:
        return
    done = sorted(
        (r for r in _tasks.values() if r["status"] in ("completed", "failed", "cancelled")),
        key=lambda r: r["created_at"],
    )
    for r in done[: len(_tasks) - MAX_RECORDS]:
        tid = r["task_id"]
        _tasks.pop(tid, None)
        _factories.pop(tid, None)
        _evicted_ids.add(tid)
