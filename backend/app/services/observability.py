"""RAG 可观测与成本归因（对齐企业级 RAG 文档第九、十节）

每次问答落一条事件：trace_id / 用户与角色 / 原始与改写 Query / 双路召回数 / 各阶段耗时
/ 命中片段与引用 / 治理拦截数 / 注入告警 / 生成字符数与 token 估算 / 成本归因。

存储：backend/data/rag_traces.jsonl（追加写，便于离线分析）+ 内存环形缓冲（供看板即时查询）。
成本：本地模型（Ollama）单价为 0；云端按 LLM_PRICE_PER_1K_TOKENS 估算，可按租户/用户归因。
"""
import json
import threading
import time
from collections import deque
from pathlib import Path

from app.config import settings
from app.core.middleware import get_trace_id
from app.services import tracing

_TRACE_PATH = Path(__file__).resolve().parents[2] / "data" / "rag_traces.jsonl"
_LOCK = threading.Lock()
_RECENT: deque = deque(maxlen=500)


def estimate_tokens(text: str) -> int:
    """粗略 token 估算：中文约 1.6 字符/token，英文约 4 字符/token，取折中 1.8"""
    return int(len(text or "") / 1.8) + 1


def cost_of(tokens: int) -> float:
    price = float(getattr(settings, "LLM_PRICE_PER_1K_TOKENS", 0.0) or 0.0)
    return round(tokens / 1000 * price, 6)


def record(event: dict) -> dict:
    """记录一条 RAG 事件（自动补 trace_id 与时间），返回落库记录"""
    rec = {
        "ts": time.time(),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "trace_id": get_trace_id(),
        **event,
    }
    tokens = rec.get("tokens") or 0
    rec["cost"] = cost_of(tokens)
    _RECENT.appendleft(rec)
    try:
        _TRACE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_TRACE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # Langfuse 链路追踪：已配置则批量上报（trace + span + generation），未配置为 no-op
    try:
        tracing.record_rag(rec)
    except Exception:
        pass
    # 审计哈希链（等保：审计日志防篡改）：RAG 事件入链
    try:
        from app.services import audit_chain
        audit_chain.append(rec)
    except Exception:
        pass
    return rec


def recent(limit: int = 50) -> list[dict]:
    return list(_RECENT)[: max(1, min(limit, 500))]


def doc_heat(limit: int = 10) -> list[dict]:
    """知识热度：按问答引用次数统计（运营：识别高价值知识与冷门/待补知识）"""
    counts: dict[str, int] = {}
    for r in _RECENT:
        for d in r.get("docs") or []:
            if d:
                counts[d] = counts.get(d, 0) + 1
    return sorted(({"doc": k, "hits": v} for k, v in counts.items()),
                  key=lambda x: -x["hits"])[:limit]


def metrics() -> dict:
    """聚合指标：调用量 / 拒答率 / 平均耗时 / 平均召回 / 拦截与注入告警 / 成本"""
    rows = list(_RECENT)
    total = len(rows)
    if not total:
        return {"total": 0, "rejected": 0, "reject_rate": 0.0, "avg_elapsed_ms": 0.0,
                "avg_recall": 0.0, "blocked_total": 0, "injection_alerts": 0,
                "total_tokens": 0, "total_cost": 0.0, "by_user": {}, "recent_low_score": [],
                "avg_faithfulness": None, "low_faith_count": 0, "cache_hits": 0, "doc_heat": []}

    rejected = sum(1 for r in rows if r.get("rejected"))
    blocked = sum(int(r.get("blocked") or 0) for r in rows)
    tokens = sum(int(r.get("tokens") or 0) for r in rows)
    faith_scores = [float(r["faithfulness"]) for r in rows if r.get("faithfulness") is not None]
    cache_hits = sum(1 for r in rows if r.get("from_cache"))
    cost = sum(float(r.get("cost") or 0.0) for r in rows)
    by_user: dict[str, int] = {}
    by_tenant: dict[str, float] = {}
    for r in rows:
        u = r.get("username") or "-"
        by_user[u] = by_user.get(u, 0) + 1
        t = r.get("tenant_id") or "default"
        by_tenant[t] = round(by_tenant.get(t, 0.0) + float(r.get("cost") or 0.0), 6)

    # 知识缺口：拒答 / 低分 / 未命中检索的 Query（供运营补文档）
    gaps = [{"query": r.get("query", ""), "score": r.get("top_score", 0.0), "time": r.get("time", "")}
            for r in rows if r.get("rejected") or float(r.get("top_score") or 0) < 0.4][:20]

    return {
        "total": total,
        "rejected": rejected,
        "reject_rate": round(rejected / total, 4),
        "avg_elapsed_ms": round(sum(float(r.get("elapsed_ms") or 0) for r in rows) / total, 1),
        "avg_recall": round(sum(float(r.get("recall_total") or 0) for r in rows) / total, 1),
        "blocked_total": blocked,
        "injection_alerts": sum(1 for r in rows if r.get("injection_flags")),
        "total_tokens": tokens,
        "total_cost": round(cost, 6),
        "by_user": by_user,
        "cost_by_tenant": by_tenant,
        "recent_low_score": gaps,
        # 幻觉检测与缓存（文档第五、十节）
        "avg_faithfulness": round(sum(faith_scores) / len(faith_scores), 3) if faith_scores else None,
        "low_faith_count": sum(1 for r in rows if r.get("faith_level") == "low"),
        "cache_hits": cache_hits,
        "doc_heat": doc_heat(10),
    }
