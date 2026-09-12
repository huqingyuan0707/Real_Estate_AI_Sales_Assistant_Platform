"""费用统计接口：演示预算数据 + 真实 RAG 调用成本归因

真实部分来自 services/observability 的问答事件：调用量 / token / 成本，
按用户与租户归因；单价由配置 LLM_PRICE_PER_1K_TOKENS 控制（本地 Ollama 为 0）。
保持演示看板原有字段结构不变，新增 real 段供前端展示真实归因。
"""
from fastapi import APIRouter

from app.config import settings
from app.core.responses import ok
from app.mock_data import COST_STATS
from app.services import observability

router = APIRouter()


@router.get("/stats")
def cost_stats():
    m = observability.metrics()
    real = {
        "qa_count": m["total"],
        "tokens": m["total_tokens"],
        "cost": m["total_cost"],
        "cost_by_tenant": m.get("cost_by_tenant", {}),
        "qa_by_user": m.get("by_user", {}),
        "avg_elapsed_ms": m["avg_elapsed_ms"],
        "avg_recall": m["avg_recall"],
        "reject_rate": m["reject_rate"],
        "price_per_1k_tokens": getattr(settings, "LLM_PRICE_PER_1K_TOKENS", 0.0),
    }
    return ok({**COST_STATS, "real": real})
