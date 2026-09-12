"""RAG 适配层：复用现有 services/rag 双路召回链路，对外提供统一 retrieve 接口。"""
from app.config import settings


class RagService:
    async def retrieve(self, query: str, user: dict | None = None, top_k: int = 5) -> list:
        try:
            from app.services import rag as rag_svc
            import asyncio

            for attr in ("aretrieve", "asearch", "retrieve", "search"):
                fn = getattr(rag_svc, attr, None)
                if fn is None:
                    continue
                try:
                    if asyncio.iscoroutinefunction(fn):
                        out = await fn(query, top_k=top_k)
                    else:
                        out = await asyncio.to_thread(fn, query, top_k=top_k)
                except TypeError:
                    try:
                        out = await fn(query) if asyncio.iscoroutinefunction(fn) else await asyncio.to_thread(fn, query)
                    except Exception:
                        continue
                docs = out.get("docs", out) if isinstance(out, dict) else out
                return self._tenant_filter(docs or [], user)[:top_k]
        except Exception:
            pass
        return []

    def _tenant_filter(self, docs: list, user: dict | None) -> list:
        # 权限过滤：仅保留用户可见知识（tenant/workspace 字段一致或无标记的公开片段）
        if user is None:
            return docs
        tid = user.get("tenant_id") or user.get("workspace_id")
        if not tid:
            return docs
        kept = []
        for d in docs:
            if not isinstance(d, dict):
                kept.append(d)
                continue
            meta = d.get("metadata", {}) or {}
            owner = meta.get("tenant_id") or meta.get("workspace_id")
            if owner in (None, tid):
                kept.append(d)
        return kept
