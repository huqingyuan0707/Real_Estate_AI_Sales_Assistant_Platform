"""长期记忆：用户偏好/组织知识（PostgreSQL/向量），复用 services/memory 授权写入。"""
import asyncio


class LongTermMemory:
    async def recall(self, user_id: str, tenant_id: str = "default", limit: int = 10) -> list:
        from app.services import memory as mem

        for attr in ("recall", "list_memories", "get_long_term"):
            fn = getattr(mem, attr, None)
            if fn is None:
                continue
            try:
                if asyncio.iscoroutinefunction(fn):
                    return await fn(tenant_id, user_id, limit) if "limit" in str(getattr(fn, "__code__", "")) else await fn(tenant_id, user_id)
                return await asyncio.to_thread(fn, tenant_id, user_id)
            except Exception:
                continue
        return []

    async def remember(self, user_id: str, content: str, authorized: bool = False,
                       tenant_id: str = "default") -> dict:
        from app.services import memory as mem

        fn = getattr(mem, "add_long_term", None) or getattr(mem, "remember", None)
        if fn is None:
            return {"status": "pending", "reason": "no long-term store"}
        if asyncio.iscoroutinefunction(fn):
            return await fn(tenant_id, user_id, content, authorized=authorized)
        return await asyncio.to_thread(fn, tenant_id, user_id, content, authorized=authorized)
