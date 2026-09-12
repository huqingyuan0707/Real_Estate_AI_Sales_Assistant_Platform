"""用户反馈与知识运营接口（企业级 RAG 第七、九节：反馈闭环 + 运营）

- POST /api/v1/feedback        提交反馈（采纳 / 不采纳 / 纠错），登录即可
- GET  /api/v1/feedback/mine   我的反馈记录
- GET  /api/v1/feedback/stats  运营看板：反馈闭环指标 + RAG 可观测指标（需 kb 权限）

闭环说明：反馈 → 低质量知识排行 / 知识缺口 Query → 驱动补文档与重跑评估。
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.middleware import get_trace_id
from app.core.rbac import get_current_user, require_perm
from app.core.responses import ok
from app.services import cache, feedback, observability, ratelimit

router = APIRouter()


class FeedbackRequest(BaseModel):
    rating: str = "up"                  # up 采纳 / down 不采纳
    thread_id: str = ""
    trace_id: str = ""
    query: str = ""
    answer: str = ""
    docs: list[str] | None = None       # 该回答引用的文档（用于差评归因到知识）
    comment: str = ""
    correction: str = ""                # 用户给出的正确答案（人工纠错）
    rejected: bool = False              # 是否属于拒答场景


@router.post("")
def submit_feedback(body: FeedbackRequest, user: dict = Depends(get_current_user)):
    rec = feedback.record(
        username=user["username"], role=user.get("role", ""),
        thread_id=body.thread_id, trace_id=body.trace_id or get_trace_id(),
        rating=body.rating, query=body.query, answer=body.answer,
        docs=body.docs, comment=body.comment, correction=body.correction,
        rejected=body.rejected,
    )
    return ok({"id": rec["id"], "rating": rec["rating"], "time": rec["time"]}, "反馈已记录，感谢您的反馈")


@router.get("/mine")
def my_feedback(limit: int = 20, user: dict = Depends(get_current_user)):
    return ok(feedback.list_events(limit, username=user["username"]))


@router.get("/stats", dependencies=[Depends(require_perm("kb"))])
def feedback_stats():
    """运营看板数据：反馈闭环（采纳率 / 差评知识 / 缺口 Query）+ RAG 可观测（耗时 / 召回 /
    拦截 / 注入 / 幻觉检测 / 成本）+ 缓存与限流状态"""
    return ok({
        "feedback": feedback.stats(),
        "rag": observability.metrics(),
        "cache": cache.stats(),
        "ratelimit": ratelimit.chat_limiter.stats(),
    })
