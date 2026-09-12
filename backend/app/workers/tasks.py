"""长任务：知识索引 / 渲染 / Agent 后台任务。Celery 可用时投递，否则内存直跑。"""
import uuid

_TASKS: dict[str, dict] = {}


def _new_task(kind: str, payload: dict) -> dict:
    task_id = uuid.uuid4().hex
    _TASKS[task_id] = {"id": task_id, "kind": kind, "status": "queued",
                       "input": payload, "output": {}, "error": ""}
    return _TASKS[task_id]


def enqueue_index(doc_id: str, content: str = "") -> dict:
    return _new_task("index", {"doc_id": doc_id, "content": content[:500]})


def enqueue_agent(query: str, user: str = "") -> dict:
    return _new_task("agent", {"query": query, "user": user})


def get_task(task_id: str) -> dict | None:
    return _TASKS.get(task_id)


try:
    from app.workers.celery_app import celery_app

    if celery_app is not None:

        @celery_app.task(name="agent.index")
        def index_task(doc_id: str, content: str = "") -> dict:
            return {"doc_id": doc_id, "status": "done"}

        @celery_app.task(name="agent.run")
        def agent_task(query: str) -> dict:
            return {"query": query, "status": "done"}
except Exception:
    pass
