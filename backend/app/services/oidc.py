"""OIDC 单点登录（对齐企业级 RAG 文档第六节：认证 SSO / OIDC / JWT）

标准授权码流程（后端交换 token，前端只拿平台 Token）：
  1) GET /auth/oidc/login           → 302 到 IdP authorize 端点（state 防 CSRF）
  2) GET /auth/oidc/callback?code&state → 校验 state → 换 id_token → 解析 claims
  3) claims 映射本地用户：preferred_username / email ↔ users.json
     命中 → 签发平台 Token；未命中且 OIDC_AUTO_CREATE → 自动创建 member；否则 403

说明：code 由后端经 TLS 直连 token endpoint 换取（client_secret 校验、一次性使用）；
id_token 签名验证（JWKS / RS256）按规范应在生产启用，此处为演示实现并已注明。

内置 mock IdP（仅 OIDC_MOCK=true 时启用）：discovery / authorize / token 三个端点
模拟标准 IdP 行为，可在本地无真实 IdP 的情况下端到端验证整个流程。
"""
import base64
import json
import secrets
import time
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.services import user_store

_state_store: dict[str, float] = {}
_DISCOVERY: dict | None = None
_MOCK_CODES: dict[str, str] = {}          # code → username（mock IdP）


def enabled() -> bool:
    return bool(settings.OIDC_ISSUER and settings.OIDC_CLIENT_ID and settings.OIDC_CLIENT_SECRET)


def status() -> dict:
    return {
        "oidc_enabled": enabled(),
        "issuer": settings.OIDC_ISSUER or "",
        "client_id": settings.OIDC_CLIENT_ID or "",
        "redirect_uri": settings.OIDC_REDIRECT_URI,
        "auto_create": settings.OIDC_AUTO_CREATE,
        "mock_idp": settings.OIDC_MOCK,
        "hint": "" if enabled() else "未配置 OIDC（OIDC_ISSUER / CLIENT_ID / CLIENT_SECRET），当前仅支持本地账号密码登录",
    }


# ---------------- state（防 CSRF） ----------------

def make_state() -> str:
    st = secrets.token_urlsafe(24)
    _state_store[st] = time.time()
    for k, t in list(_state_store.items()):
        if time.time() - t > 300:
            _state_store.pop(k, None)
    return st


def check_state(state: str) -> bool:
    t = _state_store.pop(state, None)
    return t is not None and time.time() - t <= 300


# ---------------- 端点发现与令牌交换 ----------------

def _endpoints() -> dict:
    if settings.OIDC_MOCK:
        base = settings.OIDC_ISSUER.rstrip("/")
        return {"authorization_endpoint": f"{base}/authorize",
                "token_endpoint": f"{base}/token"}
    global _DISCOVERY
    if _DISCOVERY is None:
        r = httpx.get(f"{settings.OIDC_ISSUER.rstrip('/')}/.well-known/openid-configuration", timeout=5)
        r.raise_for_status()
        _DISCOVERY = r.json()
    return _DISCOVERY


def authorize_url(state: str) -> str:
    ep = _endpoints()
    params = urlencode({
        "response_type": "code",
        "client_id": settings.OIDC_CLIENT_ID,
        "redirect_uri": settings.OIDC_REDIRECT_URI,
        "scope": settings.OIDC_SCOPES,
        "state": state,
    })
    return f"{ep['authorization_endpoint']}?{params}"


def _decode_jwt_payload(id_token: str) -> dict:
    payload = id_token.split(".")[1] if id_token.count(".") >= 1 else ""
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload))


def exchange_code(code: str) -> dict:
    """授权码 → id_token claims（后端直连 token endpoint，client_secret 校验）"""
    ep = _endpoints()
    # code 同时放 query 与 form：兼容标准 IdP（读 form）与内置 mock（读 query）
    r = httpx.post(ep["token_endpoint"], params={"code": code}, data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.OIDC_REDIRECT_URI,
        "client_id": settings.OIDC_CLIENT_ID,
        "client_secret": settings.OIDC_CLIENT_SECRET,
    }, timeout=8)
    r.raise_for_status()
    data = r.json()
    return _decode_jwt_payload(data.get("id_token") or "")


def map_user(claims: dict) -> tuple[dict | None, str]:
    """IdP claims → 本地用户（返回 user, message）"""
    username = claims.get("preferred_username") or (claims.get("email") or "").split("@")[0]
    if not username:
        return None, "IdP claims 缺少 preferred_username / email，无法映射本地账号"
    user = user_store.get(username)
    if user:
        if user.get("status") != "active":
            return None, "账号已被禁用，请联系管理员"
        return user, ""
    if not settings.OIDC_AUTO_CREATE:
        return None, f"本地不存在账号 {username}，且未开启 OIDC 自动创建"
    try:
        user_store.create_user(
            name=claims.get("name") or username,
            username=username,
            password=secrets.token_urlsafe(24),
            role="member",
            workspace=claims.get("department") or "外部登录",
        )
    except ValueError as e:
        return None, str(e)
    return user_store.get(username), "已按 IdP 身份自动创建 member 账号"


# ---------------- 内置 mock IdP（仅 OIDC_MOCK=true） ----------------

def mock_issue_code(username: str) -> str:
    code = secrets.token_urlsafe(16)
    _MOCK_CODES[code] = username
    return code


def mock_token(code: str) -> dict:
    username = _MOCK_CODES.pop(code, None)
    if not username:
        raise ValueError("无效或已使用的 mock code")
    user = user_store.get(username)
    display = user.get("name", username) if user else username
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({
        "preferred_username": username,
        "name": display,
        "email": f"{username}@corp.local",
        "iss": settings.OIDC_ISSUER,
        "exp": int(time.time()) + 300,
    }).encode()).decode().rstrip("=")
    return {"id_token": f"{header}.{payload}.mock-signature", "token_type": "id_token"}
