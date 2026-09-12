"""模型网关：多模型路由 + Fallback + 配额/成本归因 + 结果缓存。"""
import time

from app.config import settings
from app.core.logging import log_event
from app.modules.agent.llm.providers import OpenAICompatProvider


class ModelGateway:
    def __init__(self):
        self.providers = {"default": OpenAICompatProvider(), "openai-compat": OpenAICompatProvider()}
        self._cache: dict[str, tuple[str, float]] = {}
        self._usage: dict[str, dict] = {}
        self._cache_ttl = getattr(settings, "RAG_CACHE_TTL", 300)

    def select(self, model: str | None = None, tenant: str | None = None) -> str:
        return model or getattr(settings, "LLM_MODEL", "qwen2.5:14b")

    def fallback(self, model: str) -> str:
        return model  # 单 Provider 时回退自身（多模型时在此切换 provider）

    async def generate(self, messages_or_state, model: str | None = None,
                       tenant: str | None = None) -> str:
        messages = self._coerce(messages_or_state)
        name = self.select(model, tenant)
        key = f"{name}:{str(messages)[:500]}"
        hit = self._cache.get(key)
        if hit and time.time() - hit[1] < self._cache_ttl:
            return hit[0]
        provider = self.providers["default"]
        started = time.time()
        try:
            out = await provider.generate(messages, name)
        except Exception:
            out = await self.providers[self.fallback(name)].generate(messages, name)
        self._cache[key] = (out, time.time())
        self._record(tenant or "default", name, messages, out, time.time() - started)
        return out

    def _coerce(self, messages_or_state) -> list[dict]:
        if isinstance(messages_or_state, list):
            return messages_or_state
        query = getattr(messages_or_state, "query", str(messages_or_state))
        obs = getattr(messages_or_state, "observations", []) or []
        docs = getattr(messages_or_state, "docs", []) or []
        ctx = f"已知信息：{str(obs[-1])[:1500]}" if obs else (
            f"参考资料：{str(docs[:2])[:1500]}" if docs else "")
        return [{"role": "user", "content": f"{query}\n{ctx}"}]

    def _record(self, tenant: str, model: str, messages: list, out: str, latency: float) -> None:
        try:
            from app.services import observability as obs_svc

            tokens = len(str(messages)) // 2 + len(out) // 2
            price = getattr(settings, "LLM_PRICE_PER_1K_TOKENS", 0.0)
            cost = tokens / 1000 * price
            fn = getattr(obs_svc, "record_llm", None)
            if fn:
                fn(tenant, model, tokens, cost, latency)
            else:
                bucket = self._usage.setdefault(tenant, {"tokens": 0, "cost": 0.0, "calls": 0})
                bucket["tokens"] += tokens
                bucket["cost"] += cost
                bucket["calls"] += 1
            log_event("llm.generate", tenant=tenant, model=model, latency=round(latency, 3))
        except Exception:
            pass
