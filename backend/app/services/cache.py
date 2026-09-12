"""轻量 TTL 缓存（检索与生成复用，对齐企业级 RAG 文档第十节"缓存与降级策略"）

- 缓存键包含知识库版本号（rag._kb_rev）：知识库变更后自动失效，避免脏读
- 线程安全 + LRU 容量上限；单进程实现，多副本部署应替换为 Redis
- 命中率计入可观测（/feedback/stats 的 rag 段）
"""
import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Any

_MAX_ITEMS = 500


class TTLCache:
    def __init__(self, maxsize: int = _MAX_ITEMS):
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._maxsize = maxsize
        self.hits = 0
        self.misses = 0

    def get(self, key: str):
        now = time.time()
        with self._lock:
            item = self._data.get(key)
            if not item:
                self.misses += 1
                return None
            expire, value = item
            if expire < now:
                self._data.pop(key, None)
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: str, value, ttl: int) -> None:
        with self._lock:
            self._data[key] = (time.time() + ttl, value)
            self._data.move_to_end(key)
            while len(self._data) > self._maxsize:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def stats(self) -> dict:
        with self._lock:
            total = self.hits + self.misses
            return {"size": len(self._data), "hits": self.hits, "misses": self.misses,
                    "hit_rate": round(self.hits / total, 3) if total else 0.0}


retrieval_cache = TTLCache()
answer_cache = TTLCache()


def key_of(*parts) -> str:
    """稳定缓存键：把任意参数序列化为 sha1（含知识库版本号即可实现自动失效）"""
    raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode()).hexdigest()


def stats() -> dict:
    """两个缓存的汇总命中情况（供可观测指标与运营看板展示）"""
    r = retrieval_cache.stats()
    a = answer_cache.stats()
    hits = r["hits"] + a["hits"]
    total = hits + r["misses"] + a["misses"]
    return {
        "retrieval": r,
        "answer": a,
        "hits": hits,
        "hit_rate": round(hits / total, 3) if total else 0.0,
    }
