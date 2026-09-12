"""索引器：知识库更新走异步任务（分块/嵌入/入库），此处为薄封装。"""
import asyncio


class Indexer:
    async def index_document(self, doc_id: str, content: str = "", **kwargs) -> dict:
        try:
            from app.services import ingest as ingest_svc

            fn = getattr(ingest_svc, "aindex", None) or getattr(ingest_svc, "index", None)
            if fn is not None:
                if asyncio.iscoroutinefunction(fn):
                    return await fn(doc_id, content, **kwargs)
                return await asyncio.to_thread(fn, doc_id, content, **kwargs)
        except Exception as e:
            return {"doc_id": doc_id, "status": "queued", "reason": str(e)}
        # 无入库服务时降级为排队（由 workers/tasks 异步消费）
        try:
            from app.workers.tasks import enqueue_index

            enqueue_index(doc_id, content)
        except Exception:
            pass
        return {"doc_id": doc_id, "status": "queued"}
