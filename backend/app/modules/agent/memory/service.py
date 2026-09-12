"""记忆服务门面：短期 + 长期统一出口（摘要压缩防 Token 爆炸由底层负责）。"""
from app.modules.agent.memory.long_term import LongTermMemory
from app.modules.agent.memory.short_term import ShortTermMemory


class MemoryService:
    def __init__(self):
        self.short_term = ShortTermMemory()
        self.long_term = LongTermMemory()

    async def load(self, session_id: str, user_id: str, tenant_id: str = "default"):
        ctx = await self.short_term.load(session_id, user_id, tenant_id)
        try:
            prefs = await self.long_term.recall(user_id, tenant_id)
        except Exception:
            prefs = []
        return {"context": ctx, "preferences": prefs}
