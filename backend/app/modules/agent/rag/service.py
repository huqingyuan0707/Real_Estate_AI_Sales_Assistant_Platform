"""RAG 适配层：复用现有 services/rag 双路召回链路，对外提供统一 retrieve 接口。"""
import inspect


class RagService:
    async def retrieve(self, query: str, user: dict | None = None, top_k: int = 5) -> list:
        try:
            import asyncio

            from app.services import rag as rag_svc

            fn = getattr(rag_svc, "retrieve", None)
            if fn is None:
                return []
            # 按真实签名传参（retrieve(query, ctx=None, filters=None)），只传其接受的参数
            kwargs: dict = {}
            try:
                params = inspect.signature(fn).parameters
                if "top_k" in params:
                    kwargs["top_k"] = top_k
                if "ctx" in params and user is not None:
                    kwargs["ctx"] = {"user": user}
            except Exception:
                pass
            if asyncio.iscoroutinefunction(fn):
                out = await fn(query, **kwargs)
            else:
                out = await asyncio.to_thread(fn, query, **kwargs)
            # 真实返回 tuple(docs, rejected, meta)；兼容 dict/list 变体
            docs = out[0] if isinstance(out, tuple) and out else (
                out.get("docs", out) if isinstance(out, dict) else out)
            return self._tenant_filter(list(docs or []), user)[:top_k]
        except Exception:
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
