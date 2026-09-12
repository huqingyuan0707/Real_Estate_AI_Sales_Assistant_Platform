"""诊断：LLM 布局规划原始回复内容"""
import asyncio
import json
import sys

sys.path.insert(0, r"d:\Real_Estate_AI_Assistant_Platform\backend")
import httpx

from app.config import settings
from app.services.space_ai import _FALLBACK_SPACE, _LAYOUT_PROMPT


async def main() -> None:
    prompt = _LAYOUT_PROMPT.format(
        space=json.dumps(_FALLBACK_SPACE, ensure_ascii=False),
        furniture="沙发、茶几、电视机、盆栽、地毯",
        style="现代简约", scene="客厅",
    )
    async with httpx.AsyncClient(timeout=60, trust_env=False) as c:
        r = await c.post(
            f"{settings.RENDER_API_BASE.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.RENDER_API_KEY}"},
            json={
                "model": settings.SPACE_LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.5, "max_tokens": 900,
            },
        )
        print(f"status={r.status_code}")
        msg = r.json()["choices"][0]["message"]
        print(f"finish_reason={msg.get('finish_reason')}")
        print(f"content repr:\n{repr((msg.get('content') or '')[:800])}")


asyncio.run(main())
