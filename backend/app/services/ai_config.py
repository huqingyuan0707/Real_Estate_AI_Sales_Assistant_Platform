"""用户级 AI 服务配置：用户在前端「我的 AI 服务」页自行填写 Key 并保存。

存储：backend/data/user_ai_config.json（{username: {字段...}}，原子写）
生效：调用链优先用"当前用户"的配置，缺项回退全局 settings（.env）。
     因此管理员仍是系统默认口径，而每个用户可以填自己的 Key（独立计费/试用），
     保存后立即生效——不需要改 .env，也不需要重启后端。
安全：对外接口只回掩码（sk-****cdef），明文仅在服务端内存中用于发起调用；
     生产环境应换加密列（KMS）存储并加审计，本模块对外契约不变。

字段语义（空字符串 = 清除该项，回退系统默认）：
- llm_base_url / llm_api_key / llm_model              智能对话（OpenAI 兼容）
- render_api_base / render_api_key / render_api_model 生图 / 空间理解（云端）
"""
import json
import os
import threading
import time

import httpx

from app.config import settings
from app.core.user_context import current_user

_LOCK = threading.Lock()
# backend/app/services/ai_config.py → parents[2] = backend
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
_PATH = os.path.join(_DATA_DIR, "user_ai_config.json")

FIELDS = ("llm_base_url", "llm_api_key", "llm_model",
          "render_api_base", "render_api_key", "render_api_model")
SECRET_FIELDS = ("llm_api_key", "render_api_key")


# ---------------- 存储 ----------------

def _load() -> dict:
    try:
        with open(_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data: dict) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    tmp = f"{_PATH}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _PATH)  # 原子替换，避免写一半被读到


def get(username: str | None) -> dict:
    """原始配置（含明文 Key），仅服务端内部使用"""
    if not username:
        return {}
    with _LOCK:
        return dict(_load().get(username) or {})


def save(username: str, patch: dict) -> dict:
    """增量保存；值为空串表示删除该项（回退系统默认）；全部清空则移除该用户记录"""
    with _LOCK:
        data = _load()
        cur = dict(data.get(username) or {})
        for k in FIELDS:
            if k in patch and patch[k] is not None:
                v = str(patch[k]).strip()
                if v:
                    cur[k] = v
                else:
                    cur.pop(k, None)
        if cur:
            cur["updated_at"] = time.strftime("%Y-%m-%d %H:%M")
            data[username] = cur
        else:
            data.pop(username, None)
        _save(data)
        return dict(cur)


def clear(username: str) -> None:
    with _LOCK:
        data = _load()
        if data.pop(username, None) is not None:
            _save(data)


def mask(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return "****"
    return f"{secret[:4]}****{secret[-4:]}"


def public(username: str | None) -> dict:
    """对外视图：Key 掩码，附带是否已配置标记"""
    cfg = get(username)
    out = {k: cfg.get(k, "") for k in FIELDS}
    for k in SECRET_FIELDS:
        out[k] = mask(out[k])
    out["has_llm_key"] = bool(cfg.get("llm_api_key"))
    out["has_render_key"] = bool(cfg.get("render_api_key"))
    out["configured"] = bool(cfg)
    out["updated_at"] = cfg.get("updated_at", "")
    return out


# ---------------- 生效配置（用户优先 → 回退全局） ----------------

def _provider_of(base: str) -> str:
    b = (base or "").lower()
    if "aliyuncs" in b or "dashscope" in b:
        return "dashscope"
    if "siliconflow" in b:
        return "siliconflow"
    return "auto"


def effective_llm() -> dict:
    """当前生效的对话模型配置（llm.py 调用前取用）"""
    cfg = get(current_user())
    user_key = cfg.get("llm_api_key") or ""
    return {
        "base_url": cfg.get("llm_base_url") or settings.LLM_BASE_URL,
        "api_key": user_key or settings.LLM_API_KEY,
        "model": cfg.get("llm_model") or settings.LLM_MODEL,
        "source": "user" if user_key else "system",
    }


def effective_render() -> dict:
    """当前生效的生图/空间理解配置（render.py / space_ai.py / furniture.py 取用）"""
    cfg = get(current_user())
    user_key = cfg.get("render_api_key") or ""
    base = cfg.get("render_api_base") or ""
    # 用户改了服务地址时按地址推断厂商，否则沿用系统 provider
    provider = _provider_of(base) if base else settings.RENDER_PROVIDER
    return {
        "base_url": base or settings.RENDER_API_BASE,
        "api_key": user_key or settings.RENDER_API_KEY,
        "model": cfg.get("render_api_model") or settings.RENDER_API_MODEL,
        "provider": provider,
        "source": "user" if (user_key or base) else "system",
    }


# ---------------- 连通性探测 ----------------

async def probe(base_url: str, api_key: str, timeout: float = 15.0) -> dict:
    """探测 OpenAI 兼容服务（GET /models）。返回 {ok, message, status?}"""
    base = (base_url or "").rstrip("/")
    if not base:
        return {"ok": False, "message": "服务地址为空，请先填写 Base URL"}
    if "aliyuncs" in base.lower() or "dashscope" in base.lower():
        return {"ok": None, "message": "通义万相未提供 /models 探测接口，保存后在生图任务中验证即可"}
    if not api_key:
        return {"ok": False, "message": "API Key 为空"}
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as c:
            r = await c.get(f"{base}/models", headers={"Authorization": f"Bearer {api_key}"})
        if r.status_code == 200:
            return {"ok": True, "message": "连接成功，Key 可用", "status": 200}
        if r.status_code in (401, 403):
            return {"ok": False, "message": f"Key 无效或无权限（HTTP {r.status_code}）", "status": r.status_code}
        return {"ok": False, "message": f"服务返回 HTTP {r.status_code}", "status": r.status_code}
    except Exception as e:
        return {"ok": False, "message": f"连接失败：{type(e).__name__}（请检查地址与网络）"}
