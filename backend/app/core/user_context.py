"""当前请求用户上下文（ContextVar）：供服务层按用户取 AI 配置。

设置点：core/rbac.py::get_current_user（async，运行在请求所属 task 内）
读取点：services/ai_config.py 的 effective_llm() / effective_render()
说明：task_center 用 asyncio.create_task 提交后台任务，会复制当前 context，
     因此生图等后台任务内仍能读到"提交者"的配置；无用户上下文时回退全局 .env。
"""
from contextvars import ContextVar

_current_username: ContextVar[str | None] = ContextVar("current_username", default=None)


def set_current_user(username: str | None) -> None:
    _current_username.set(username)


def current_user() -> str | None:
    return _current_username.get()
