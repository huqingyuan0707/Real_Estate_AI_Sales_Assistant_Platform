"""诊断：硅基流动 chat/completions 可用模型与 VLM 真实报错"""
import asyncio
import sys

sys.path.insert(0, r"d:\Real_Estate_AI_Assistant_Platform\backend")
import httpx

from app.config import settings

ONE_PX = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


async def main() -> None:
    base = settings.RENDER_API_BASE.rstrip("/")
    print(f"base={base} key_set={bool(settings.RENDER_API_KEY)} vlm={settings.SPACE_VLM_MODEL} llm={settings.SPACE_LLM_MODEL}")
    async with httpx.AsyncClient(timeout=30, trust_env=False) as c:
        h = {"Authorization": f"Bearer {settings.RENDER_API_KEY}"}
        r = await c.get(f"{base}/models", headers=h)
        models = [m["id"] for m in r.json().get("data", [])]
        print(f"[models] total={len(models)} VL/chat candidates:")
        for m in models:
            if "vl" in m.lower() or "vision" in m.lower():
                print("   VL:", m)
        for m in models:
            if "qwen" in m.lower() and "instruct" in m.lower() and "vl" not in m.lower():
                print("   LLM:", m)
        r2 = await c.post(f"{base}/chat/completions", headers=h, json={
            "model": settings.SPACE_VLM_MODEL,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{ONE_PX}"}},
                {"type": "text", "text": "describe in 5 words"},
            ]}],
            "max_tokens": 50,
        })
        print(f"[vlm-call] status={r2.status_code} body={r2.text[:300]}")


asyncio.run(main())
