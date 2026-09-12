"""密码策略与登录失败锁定（等保三级「身份鉴别」）

- 密码强度：最小长度 + 大小写 + 数字（创建用户 / 重置密码时校验）
- 失败锁定：同一账号连续失败 LOGIN_FAIL_LIMIT 次后锁定 LOGIN_LOCK_SECONDS 秒
进程内实现，多副本部署应换集中式存储。
"""
import threading
import time

from app.config import settings

_LOCKS: dict[str, list[float]] = {}
_LOCK = threading.Lock()


def validate(password: str) -> list[str]:
    """返回违规项列表；空列表 = 通过"""
    pwd = password or ""
    issues: list[str] = []
    if len(pwd) < settings.PASSWORD_MIN_LEN:
        issues.append(f"长度不足 {settings.PASSWORD_MIN_LEN} 位")
    if not any(c.islower() for c in pwd):
        issues.append("缺少小写字母")
    if not any(c.isupper() for c in pwd):
        issues.append("缺少大写字母")
    if not any(c.isdigit() for c in pwd):
        issues.append("缺少数字")
    return issues


def locked_remaining(username: str) -> int:
    """处于锁定期则返回剩余秒数，否则 0"""
    now = time.time()
    with _LOCK:
        fails = [t for t in _LOCKS.get(username, []) if now - t < settings.LOGIN_LOCK_SECONDS]
    if len(fails) >= settings.LOGIN_FAIL_LIMIT:
        return int(settings.LOGIN_LOCK_SECONDS - (now - fails[0]))
    return 0


def record_fail(username: str) -> None:
    now = time.time()
    with _LOCK:
        q = [t for t in _LOCKS.get(username, []) if now - t < settings.LOGIN_LOCK_SECONDS]
        q.append(now)
        _LOCKS[username] = q


def reset(username: str) -> None:
    with _LOCK:
        _LOCKS.pop(username, None)


def stats() -> dict:
    now = time.time()
    with _LOCK:
        active = {u: len([t for t in q if now - t < settings.LOGIN_LOCK_SECONDS])
                  for u, q in _LOCKS.items() if q}
    return {"min_len": settings.PASSWORD_MIN_LEN,
            "fail_limit": settings.LOGIN_FAIL_LIMIT,
            "lock_seconds": settings.LOGIN_LOCK_SECONDS,
            "users_with_failures": {u: n for u, n in active.items() if n}}
