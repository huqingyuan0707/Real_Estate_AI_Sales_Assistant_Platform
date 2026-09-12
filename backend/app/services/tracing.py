"""Langfuse 链路追踪适配器（对齐企业级 RAG 文档第九节：全链路 Trace / LLM Trace）

**零 SDK 实现**：配置 LANGFUSE_HOST + PUBLIC_KEY + SECRET_KEY 后，按 Langfuse Ingestion API
（POST {host}/api/public/ingestion，Basic Auth）批量上报 trace / span / generation；
未配置时不外发任何请求——一切只保留本地 JSONL（services/observability），行为完全一致。

上报结构（对齐第九节"每次问答：Query、召回、重排、Prompt、生成、引用"）：
  trace-create   id=trace_id, userId, sessionId, input=问题, output=回答, metadata=质量与治理指标
  ├ span-create  rag.retrieve（双路召回数 / 各阶段耗时 / 治理拦截 / 注入告警）
  └ generation-create  llm.generate（model / token 用量 / key 来源）

失败不阻塞主链路：上报错误计数并在 status() 暴露，缓冲有界防内存膨胀。
"""
import threading
import time
import uuid

import httpx

from app.config import settings

_LOCK = threading.Lock()
_BUFFER: list[dict] = []
_STATS = {"sent": 0, "errors": 0, "last_error": ""}


def enabled() -> bool:
    return bool(settings.LANGFUSE_HOST and settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY)


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts))


def _event(etype: str, body: dict) -> dict:
    return {"id": uuid.uuid4().hex, "type": etype, "timestamp": _iso(time.time()), "body": body}


def record_rag(rec: dict) -> None:
    """把一次 RAG 问答事件转换为 Langfuse trace + span + generation 并入队"""
    if not enabled():
        return
    tid = rec.get("trace_id") or uuid.uuid4().hex
    ts = float(rec.get("ts") or time.time())
    elapsed_s = float(rec.get("elapsed_ms") or 0) / 1000
    start, end = _iso(ts - elapsed_s), _iso(ts)

    trace_body = {
        "id": tid, "timestamp": end, "name": "rag_qa",
        "userId": rec.get("username") or "-",
        "sessionId": rec.get("thread_id") or "",
        "input": rec.get("query"),
        "output": (rec.get("answer") or "")[:2000],
        "metadata": {
            "tenant_id": rec.get("tenant_id"), "role": rec.get("role"), "dept": rec.get("dept"),
            "recall_vector": rec.get("recall_vector"), "recall_keyword": rec.get("recall_bm25"),
            "blocked": rec.get("blocked"), "rejected": rec.get("rejected"),
            "top_score": rec.get("top_score"), "faithfulness": rec.get("faithfulness"),
            "faith_level": rec.get("faith_level"), "model": rec.get("model"),
            "query_expansion": rec.get("rewritten_query"),
        },
    }
    retrieve_span = _event("span-create", {
        "id": uuid.uuid4().hex, "traceId": tid, "name": "rag.retrieve",
        "startTime": start, "endTime": end,
        "metadata": {
            "recall_vector": rec.get("recall_vector"), "recall_keyword": rec.get("recall_bm25"),
            "stage_ms": rec.get("stage_ms", {}), "blocked": rec.get("blocked"),
            "blocked_reasons": rec.get("blocked_reasons", []),
            "injection_flags": rec.get("injection_flags", []),
            "from_cache": rec.get("from_cache"),
        },
    })
    generation = _event("generation-create", {
        "id": uuid.uuid4().hex, "traceId": tid, "name": "llm.generate",
        "model": rec.get("model"),
        "startTime": start, "endTime": end,
        "usage": {"total": rec.get("tokens") or 0},
        "metadata": {"key_source": rec.get("key_source"), "answer_chars": rec.get("answer_chars"),
                     "cost": rec.get("cost")},
    })

    with _LOCK:
        _BUFFER.extend([_event("trace-create", trace_body), retrieve_span, generation])
        overflow = len(_BUFFER) - 300
        if overflow > 0:
            del _BUFFER[:overflow]      # 有界缓冲，防止 IdP 长期不可用导致内存膨胀
        should_flush = len(_BUFFER) >= max(1, settings.LANGFUSE_BATCH_SIZE)
    if should_flush:
        flush()


def flush() -> dict | None:
    """批量上报；网络失败时把批次放回队首，等待下次重试"""
    if not enabled():
        return None
    with _LOCK:
        if not _BUFFER:
            return None
        batch = _BUFFER[:]
        _BUFFER.clear()
    url = f"{settings.LANGFUSE_HOST.rstrip('/')}/api/public/ingestion"
    try:
        r = httpx.post(url, json={"batch": batch},
                       auth=(settings.LANGFUSE_PUBLIC_KEY, settings.LANGFUSE_SECRET_KEY),
                       timeout=5)
        if r.status_code in (200, 201, 207):
            _STATS["sent"] += len(batch)
            return {"status": r.status_code, "sent": len(batch)}
        _STATS["errors"] += 1
        _STATS["last_error"] = f"HTTP {r.status_code}"
        with _LOCK:
            _BUFFER[:0] = batch[-100:]      # 回队首重试（有界）
        return {"status": r.status_code}
    except Exception as e:
        _STATS["errors"] += 1
        _STATS["last_error"] = f"{type(e).__name__}: {str(e)[:120]}"
        with _LOCK:
            _BUFFER[:0] = batch[-100:]
        return {"error": _STATS["last_error"]}


def status() -> dict:
    """追踪状态（诊断与合规自查）：是否启用、上报量、错误"""
    return {
        "langfuse_enabled": enabled(),
        "langfuse_host": settings.LANGFUSE_HOST or "",
        "buffered": len(_BUFFER),
        **_STATS,
        "hint": "" if enabled() else "未配置 Langfuse（LANGFUSE_HOST/PUBLIC_KEY/SECRET_KEY），当前仅本地 JSONL",
    }
