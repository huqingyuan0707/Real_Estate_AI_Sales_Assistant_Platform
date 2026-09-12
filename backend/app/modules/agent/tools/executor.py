"""工具执行器：鉴权 → 幂等（缓存）→ 执行 → 审计；超时/重试由调用方配置。"""
import asyncio
import inspect
import time
from typing import Any

from app.core.logging import log_event
from app.modules.agent.tools.registry import registry as registry_module


class ToolExecutor:
    def __init__(self, cache=None, timeout: float = 30.0, registry=None):
        self._idem: dict[str, tuple[Any, float]] = {}
        self._timeout = timeout
        self._cache = cache  # 可选外部缓存（Redis），无则用进程内存
        self._registry = registry or registry_module
        try:
            from app.services import cache as cache_svc  # 复用现有缓存服务
            self._cache_svc = cache_svc
        except Exception:
            self._cache_svc = None

    def _allowed(self, tool: dict, user: dict | None) -> bool:
        if not tool["scopes"]:
            return True
        if user is None:
            return False
        if user.get("role") == "admin":
            return True
        from app.core.rbac import permissions_of

        return set(tool["scopes"]) <= permissions_of(user.get("role", ""))

    async def execute(self, action, user: dict | None = None):
        tool = self._registry.get(action.name)
        if not self._allowed(tool, user):
            raise PermissionError("tool not allowed")
        key = getattr(action, "idempotency_key", None)
        if tool["idempotent"] and key:
            hit = self._idem.get(key)
            if hit:
                return hit[0]
        handler = tool["handler"]
        try:
            if inspect.iscoroutinefunction(handler):
                result = await asyncio.wait_for(handler(**action.args), self._timeout)
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(handler, **action.args), self._timeout)
        except Exception:
            raise
        if tool["idempotent"] and key:
            self._idem[key] = (result, time.time())
        try:
            log_event("tool.call", name=action.name,
                      user=(user or {}).get("username", "anonymous"))
        except Exception:
            pass
        return result
