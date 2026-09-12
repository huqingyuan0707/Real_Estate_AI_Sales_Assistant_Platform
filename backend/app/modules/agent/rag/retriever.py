"""检索器：embedding → 向量检索(top_k) → 重排 → 引用裁剪。复用 services 层实现。"""
from app.modules.agent.rag.service import RagService


class Retriever(RagService):
    async def search(self, query: str, user: dict | None = None, top_k: int = 5):
        return await self.retrieve(query, user, top_k=top_k)
