"""审计日志接口：真实 RAG 审计 + 演示历史数据

真实记录来自 services/observability 的 RAG 事件，回答"谁、何时、问了什么、看了哪些知识"：
user / role / query / 命中文档 / 治理拦截数 / 注入告警 / 耗时 / 成本 / trace_id。
"""
from fastapi import APIRouter, Depends

from app.core.rbac import require_perm
from app.core.responses import ok
from app.mock_data import AUDIT_DETAIL_DIALOG, AUDIT_LOGS
from app.services import audit_chain, feedback, observability

router = APIRouter()


def _project(rec: dict, idx: int) -> dict:
    """把 RAG 事件投影为审计记录（字段与前端表格兼容，额外带安全与治理信息）"""
    flags = rec.get("injection_flags") or []
    return {
        "id": f"rag-{idx}",
        "time": rec.get("time", ""),
        "user": rec.get("username") or "-",
        "role": rec.get("role", ""),
        "action": "智能问答（RAG 检索增强）",
        "skill": "knowledge_qa",
        "query": rec.get("query", ""),
        "docs": rec.get("docs", []),
        "hits": rec.get("hits", []),
        "blocked": rec.get("blocked", 0),
        "blocked_reasons": rec.get("blocked_reasons", []),
        "rejected": rec.get("rejected", False),
        "cost": rec.get("cost", 0.0),
        "elapsed_ms": rec.get("elapsed_ms", 0),
        "stage_ms": rec.get("stage_ms", {}),
        "trace_id": rec.get("trace_id", ""),
        "security": bool(flags) or bool(rec.get("blocked")),
        "injection_flags": flags,
        "real": True,
    }


def real_logs(limit: int = 200) -> list[dict]:
    return [_project(r, i) for i, r in enumerate(observability.recent(limit))]


@router.get("/logs")
def list_audit_logs():
    """真实审计（时间倒序）在前，演示历史数据在后"""
    return ok([*real_logs(), *AUDIT_LOGS])


@router.get("/logs/{log_id}/detail")
def audit_log_detail(log_id: str):
    if log_id.startswith("rag-"):
        rec = next((x for x in real_logs() if x["id"] == log_id), None)
        if rec:
            return ok({
                "log_id": log_id,
                "record": rec,
                "dialog": [
                    {"role": "user", "content": rec.get("query", "")},
                    {"role": "assistant",
                     "content": "命中知识：" + ("、".join(rec.get("docs") or []) or "无（拒答或未检索）")},
                ],
            })
    return ok({"log_id": log_id, "dialog": AUDIT_DETAIL_DIALOG})


@router.get("/verify", dependencies=[Depends(require_perm("audit"))])
def verify_audit_chain():
    """审计哈希链完整性校验（等保：审计记录防篡改）；可重算全链并定位断点"""
    result = audit_chain.verify()
    msg = ("审计链完整，未被篡改" if result["valid"]
           else f"审计链校验失败，断点：第 {result['broken_at']} 条（可能被篡改或删除）")
    return ok(result, msg)


@router.get("/security")
def security_events():
    """安全事件视图：提示注入命中与被治理拦截的问答（越权检测与告警依据）"""
    rows = observability.recent(200)
    events = []
    for r in rows:
        if r.get("injection_flags") or r.get("blocked"):
            events.append({
                "time": r.get("time"), "user": r.get("username"), "query": r.get("query"),
                "blocked": r.get("blocked", 0), "blocked_reasons": r.get("blocked_reasons", []),
                "injection_flags": r.get("injection_flags", []), "trace_id": r.get("trace_id", ""),
            })
    return ok({"total": len(events), "events": events[:50],
               "feedback_alerts": [r for r in feedback.list_events(50) if r.get("rejected")][:10]})
