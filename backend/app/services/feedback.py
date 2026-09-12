"""用户反馈闭环与知识运营（对齐企业级 RAG 文档第七、九节）

每次回答的用户反馈（点赞 / 点踩 / 纠错）落库，并据此产出在线质量指标与运营洞察：
- 采纳率、差评率（在线评估）
- 差评关联的知识文档排行 → 低质量知识识别
- 差评 / 拒答 Query 聚合 → 知识缺口分析，驱动补文档

存储：backend/data/feedback_events.jsonl（追加写）+ 内存环形缓冲（看板即时查询）。
"""
import json
import threading
import time
from collections import deque
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "data" / "feedback_events.jsonl"
_LOCK = threading.Lock()
_RECENT: deque = deque(maxlen=1000)


def record(*, username: str, role: str = "", tenant_id: str = "default", thread_id: str = "",
           trace_id: str = "", rating: str = "up", query: str = "", answer: str = "",
           docs: list[str] | None = None, comment: str = "", correction: str = "",
           rejected: bool = False) -> dict:
    """记录一条反馈。rating: up 采纳 / down 不采纳"""
    rec = {
        "id": f"fb-{int(time.time() * 1000)}",
        "ts": time.time(),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "username": username, "role": role, "tenant_id": tenant_id,
        "thread_id": thread_id, "trace_id": trace_id,
        "rating": "down" if rating == "down" else "up",
        "query": (query or "")[:200],
        "answer": (answer or "")[:300],
        "docs": docs or [],
        "comment": (comment or "")[:300],
        "correction": (correction or "")[:500],
        "rejected": bool(rejected),
    }
    _RECENT.appendleft(rec)
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return rec


def list_events(limit: int = 100, username: str | None = None) -> list[dict]:
    rows = [r for r in _RECENT if not username or r.get("username") == username]
    return rows[: max(1, min(limit, 500))]


def stats() -> dict:
    """反馈聚合：采纳率 / 差评知识排行 / 缺口 Query"""
    rows = list(_RECENT)
    total = len(rows)
    up = sum(1 for r in rows if r["rating"] == "up")
    down = total - up

    by_doc: dict[str, dict] = {}
    for r in rows:
        for doc in r.get("docs") or []:
            d = by_doc.setdefault(doc, {"doc": doc, "up": 0, "down": 0})
            d[r["rating"]] += 1

    gaps: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        if r["rating"] == "down" or r.get("rejected"):
            q = (r.get("query") or "").strip()
            if q and q not in seen:
                seen.add(q)
                gaps.append({
                    "query": q,
                    "reason": "差评" if r["rating"] == "down" else "拒答",
                    "docs": r.get("docs") or [],
                    "time": r.get("time", ""),
                })

    low_quality = sorted(by_doc.values(), key=lambda d: (-d["down"], d["up"]))[:10]
    return {
        "total": total,
        "up": up,
        "down": down,
        "adoption_rate": round(up / total, 4) if total else 0.0,
        "low_quality_docs": [d for d in low_quality if d["down"] > 0],
        "gap_queries": gaps[:20],
        "recent": rows[:20],
    }
