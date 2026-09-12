"""LLM-as-judge：答案质量自动打分（对齐企业级 RAG 文档第七节"LLM-as-judge 自动打分"）

对一次问答的（问题 / 参考片段 / 答案）用 LLM 按四维打 1~5 分并给出一句理由：
相关性 relevance、依据性 groundedness（是否都来自资料、无编造）、完整性 completeness、可读性 clarity。

用于离线评估（tests/eval_rag.py --judge）与在线抽样评估；LLM 不可用时返回 available=False，
绝不阻塞主链路。
"""
import json
import re

_PROMPT = """你是 RAG 答案质量评审员。依据下面给出的资料与回答，按 1~5 分打分（5 为最好）。
评分维度：relevance 相关性、groundedness 依据性（是否全部来自资料、无编造）、
completeness 完整性、clarity 可读性。
只输出 JSON，不要任何解释：{{"relevance":n,"groundedness":n,"completeness":n,"clarity":n,"reason":"一句话理由"}}

【资料】
{context}

【问题】
{question}

【回答】
{answer}
"""


def _extract_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except Exception:
        return None


async def score(question: str, answer: str, hits: list[dict]) -> dict:
    """返回 {available, dimensions, overall, reason}；LLM 不可用则 available=False"""
    from app.services.llm import LLMUnavailable, llm_available, llm_stream

    if not (question or "").strip() or not (answer or "").strip():
        return {"available": False, "reason": "问题或答案为空"}
    if not await llm_available():
        return {"available": False, "reason": "LLM 不可用（无法自动评分）"}

    context = "\n\n".join((h.get("text") or "")[:600] for h in (hits or [])[:4]) or "（无检索资料）"
    prompt = _PROMPT.format(context=context, question=question[:400], answer=answer[:1500])
    try:
        out = ""
        async for piece in llm_stream([{"role": "user", "content": prompt}]):
            out += piece
    except LLMUnavailable as e:
        return {"available": False, "reason": f"LLM 调用失败：{str(e)[:120]}"}

    data = _extract_json(out) or {}
    dims = {k: data.get(k) for k in ("relevance", "groundedness", "completeness", "clarity")}
    vals = [float(v) for v in dims.values() if isinstance(v, (int, float))]
    return {
        "available": True,
        "dimensions": dims,
        "overall": round(sum(vals) / len(vals), 2) if vals else None,
        "reason": str(data.get("reason", ""))[:200],
    }
