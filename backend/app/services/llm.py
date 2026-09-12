"""LLM 服务层：OpenAI 兼容协议调用 Qwen2.5（Ollama / vLLM / LM Studio / 云端）

Key 来源：services/ai_config.effective_llm() —— 当前用户在前端「我的 AI 服务」保存的配置优先，
未配置时回退全局 .env，因此用户自填 Key 后无需改配置或重启即生效。

约定：
- llm_available(): 探测服务是否可达（2s 超时）
- llm_stream(messages): 异步流式返回增量文本；连接/推理异常抛 LLMUnavailable，
  由端点层降级为演示模式（保证无 GPU 开发机可完整演示）
"""
import logging

import httpx

from app.config import settings
from app.services.ai_config import effective_llm

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是房地产销售团队的 AI 助手。职责：户型讲解、文案生成、政策问答、房源分析。"
    "回答要求：1) 简洁专业，多用短句和列表；2) 涉及价格/政策时提醒以官方口径为准；"
    "3) 输出内容将被展示给客户，须标注仅供营销参考。"
)


class LLMUnavailable(Exception):
    """LLM 服务不可用（未部署/网络失败），调用方应降级"""


def _client() -> httpx.AsyncClient:
    cfg = effective_llm()
    return httpx.AsyncClient(
        base_url=cfg["base_url"],
        headers={"Authorization": f"Bearer {cfg['api_key']}"},
        timeout=httpx.Timeout(settings.LLM_TIMEOUT, connect=3.0),
    )


async def llm_available() -> bool:
    """探测 OpenAI 兼容服务（GET /models）"""
    if not settings.LLM_ENABLED:
        return False
    try:
        async with _client() as c:
            r = await c.get("/models")
            return r.status_code == 200
    except Exception:
        return False


async def llm_stream(messages: list[dict]):
    """流式对话：yield 增量文本片段。服务不可用/中断时抛 LLMUnavailable"""
    cfg = effective_llm()
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *messages],
        "stream": True,
        "temperature": 0.7,
    }
    try:
        async with _client() as c:
            async with c.stream("POST", "/chat/completions", json=payload) as r:
                if r.status_code != 200:
                    # 落日志便于定位（模型名写错 / 服务未启动 / Key 失效），否则故障静默降级无迹可循
                    body = (await r.aread()).decode("utf-8", "replace")[:200]
                    logger.warning("LLM 生成失败 HTTP %s | model=%s | base_url=%s | %s",
                                   r.status_code, cfg.get("model"), cfg.get("base_url"), body)
                    raise LLMUnavailable(f"LLM HTTP {r.status_code}")
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    import json
                    chunk = json.loads(data)
                    delta = (chunk.get("choices") or [{}])[0].get("delta", {})
                    piece = delta.get("content") or ""
                    if piece:
                        yield piece
    except LLMUnavailable:
        raise
    except Exception as e:  # 网络中断/超时/JSON 异常 → 统一降级
        logger.warning("LLM 调用异常，已降级兜底 | model=%s | base_url=%s | %s: %s",
                       cfg.get("model"), cfg.get("base_url"), type(e).__name__, e)
        raise LLMUnavailable(str(e)) from e
