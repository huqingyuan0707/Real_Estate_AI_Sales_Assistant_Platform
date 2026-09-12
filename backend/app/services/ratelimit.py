"""用户级滑动窗口限流（对齐企业级 RAG 文档第十节"限流、降级"，错误码 2002）

按 (用户, 通道) 记录最近 60 秒的调用时间戳，超限直接拒绝并回报剩余配额；
本地单进程实现，多副本部署应替换为 Redis + 令牌桶。
"""
import threading
import time
from collections import defaultdict, deque

_WINDOW = 60


class RateLimiter:
    def __init__(self, limit: int):
        self.limit = max(1, int(limit))
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        """返回 (是否放行, 剩余配额)"""
        now = time.time()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > _WINDOW:
                q.popleft()
            if len(q) >= self.limit:
                return False, 0
            q.append(now)
            return True, self.limit - len(q)

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def stats(self) -> dict:
        with self._lock:
            active = sum(1 for q in self._hits.values() if q)
            return {"window_seconds": _WINDOW, "limit_per_min": self.limit, "active_users": active}


# 会话问答通道限流单例（配额由配置 RAG_RATE_LIMIT_PER_MIN 控制）
from app.config import settings as _settings  # noqa: E402

chat_limiter = RateLimiter(_settings.RAG_RATE_LIMIT_PER_MIN)


def stats() -> dict:
    """模块级汇总（供合规报表与运营看板）"""
    return chat_limiter.stats()
