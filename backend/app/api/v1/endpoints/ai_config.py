"""我的 AI 服务配置接口（用户级，登录即可访问，不需要 settings 权限）。

- GET    /api/v1/ai-config       查看我的配置（Key 掩码）+ 系统默认 + 当前生效来源
- PUT    /api/v1/ai-config       保存（增量；字段传空串 = 清除该项，回退系统默认）
- DELETE /api/v1/ai-config       清除我的全部配置
- POST   /api/v1/ai-config/test  连通性测试（可带未保存的临时值）
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import settings
from app.core.rbac import get_current_user
from app.core.responses import ok
from app.services import ai_config as svc

router = APIRouter()


class AiConfigUpdate(BaseModel):
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    render_api_base: str | None = None
    render_api_key: str | None = None
    render_api_model: str | None = None


class AiConfigTest(BaseModel):
    target: str = "llm"           # llm / render
    base_url: str | None = None   # 不传则用已保存配置 → 系统默认
    api_key: str | None = None    # 不传（或空）则用已保存的 Key


def _safe_effective(cfg: dict) -> dict:
    """生效配置的对外视图：剥离明文 Key，只回掩码"""
    out = {k: v for k, v in cfg.items() if k != "api_key"}
    out["api_key_masked"] = svc.mask(cfg.get("api_key", ""))
    return out


@router.get("")
def get_my_ai_config(user: dict = Depends(get_current_user)):
    return ok({
        "config": svc.public(user["username"]),
        "system_defaults": {
            "llm_base_url": settings.LLM_BASE_URL,
            "llm_model": settings.LLM_MODEL,
            "llm_key_masked": svc.mask(settings.LLM_API_KEY),
            "render_api_base": settings.RENDER_API_BASE,
            "render_api_model": settings.RENDER_API_MODEL,
            "render_key_masked": svc.mask(settings.RENDER_API_KEY),
            "render_provider": settings.RENDER_PROVIDER,
        },
        "effective": {
            "llm": _safe_effective(svc.effective_llm()),
            "render": _safe_effective(svc.effective_render()),
        },
    })


@router.put("")
def update_my_ai_config(body: AiConfigUpdate, user: dict = Depends(get_current_user)):
    patch = body.model_dump(exclude_unset=True)
    saved = svc.save(user["username"], patch)
    return ok({
        "config": svc.public(user["username"]),
        "effective": {"llm": _safe_effective(svc.effective_llm()), "render": _safe_effective(svc.effective_render())},
    }, "已保存，立即生效" if saved else "已清除自定义配置，回退系统默认")


@router.delete("")
def clear_my_ai_config(user: dict = Depends(get_current_user)):
    svc.clear(user["username"])
    return ok({"config": svc.public(user["username"])}, "已清除，全部回退系统默认")


@router.post("/test")
async def test_my_ai_config(body: AiConfigTest, user: dict = Depends(get_current_user)):
    """连通性测试：优先用请求携带的临时值，缺失项回退已保存配置 → 系统默认"""
    cfg = svc.get(user["username"])
    if body.target == "render":
        eff = svc.effective_render()
        base = (body.base_url or "").strip() or cfg.get("render_api_base") or eff["base_url"]
        key = (body.api_key or "").strip() or cfg.get("render_api_key") or eff["api_key"]
    else:
        eff = svc.effective_llm()
        base = (body.base_url or "").strip() or cfg.get("llm_base_url") or eff["base_url"]
        key = (body.api_key or "").strip() or cfg.get("llm_api_key") or eff["api_key"]
    result = await svc.probe(base, key)
    return ok({"target": body.target, "base_url": base, **result})
