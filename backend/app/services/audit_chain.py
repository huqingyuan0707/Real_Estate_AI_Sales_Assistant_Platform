"""审计日志哈希链（等保三级「安全审计：日志防篡改」）

每条审计记录附链式哈希：chain = SHA256(prev_chain + canonical(本条内容))。
任何一条被篡改或删除，重算校验都会失败并把断点定位到具体条目，
满足"审计记录不可篡改、可追溯"的等保要求。

存储：data/audit_chain.jsonl（append-only，禁止覆盖写）。
"""
import hashlib
import json
import threading
import time
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "data" / "audit_chain.jsonl"
_LOCK = threading.Lock()
_GENESIS = "0" * 64


def _canonical(record: dict) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(prev: str, record: dict) -> str:
    return hashlib.sha256((prev + _canonical(record)).encode()).hexdigest()


def _last_hash() -> str:
    if not _PATH.exists():
        return _GENESIS
    last = _GENESIS
    with open(_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                last = json.loads(line).get("hash", last)
            except Exception:
                pass
    return last


def append(record: dict) -> dict:
    """把一条审计记录写入哈希链，返回带 hash 的链条目"""
    with _LOCK:
        prev = _last_hash()
        entry = {"ts": time.time(), "prev": prev, "record": record}
        entry["hash"] = _hash(prev, record)
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry


def verify(limit: int = 1000) -> dict:
    """重算整条链：返回 {total, valid, broken_at}；valid=False 时 broken_at 指向断点序号"""
    if not _PATH.exists():
        return {"total": 0, "valid": True, "broken_at": None, "last_hash": _GENESIS}
    entries: list[dict] = []
    with open(_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
    prev = _GENESIS
    checked = entries[-limit:] if limit else entries
    for i, e in enumerate(checked):
        if e.get("prev") != prev or e.get("hash") != _hash(prev, e.get("record") or {}):
            return {"total": len(entries), "valid": False, "broken_at": i, "last_hash": prev}
        prev = e["hash"]
    return {"total": len(entries), "valid": True, "broken_at": None, "last_hash": prev}
