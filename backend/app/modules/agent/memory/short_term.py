"""短期记忆：会话上下文（滑动窗口），复用 services/memory。"""
import asyncio


class ShortTermMemory:
    async def load(self, session_id: str, user_id: str, tenant_id: str = "default"):
        from app.services import memory as mem

        fn = getattr(mem, "get_context", None)
        if fn is None:
            return None
        if asyncio.iscoroutinefunction(fn):
            return await fn(tenant_id, user_id, session_id)
        return await asyncio.to_thread(fn, tenant_id, user_id, session_id)

    async def save(self, session_id: str, user_id: str, role: str, content: str,
                   tenant_id: str = "default") -> None:
        from app.services import memory as mem

        fn = getattr(mem, "add_message", None)
        if fn is None:
            return
        if asyncio.iscoroutinefunction(fn):
            await fn(tenant_id, user_id, session_id, role, content)
        else:
            await asyncio.to_thread(fn, tenant_id, user_id, session_id, role, content)
