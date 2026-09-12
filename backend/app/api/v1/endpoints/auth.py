"""认证接口：本地账号密码 / LDAP 域账号 / OIDC 单点登录 / TOTP 双因素 / 失败锁定

对齐企业级 RAG 文档第六节（认证）与等保三级「身份鉴别」控制点：
- local：users.json 账号密码 + 可选 TOTP 动态口令（RFC 6238）
- ldap：LDAP 绑定鉴别（本地须有同名账号；LDAP_URI 未配置时给出明确指引）
- oidc：标准授权码流程（state 防 CSRF；内置 mock IdP 仅 OIDC_MOCK=true 时可用于本地验证）
- 安全：连续登录失败锁定（2002 限流语义）；登录成功签发 HMAC Token 并返回权限集
- 审计：登录事件写入哈希链（audit_chain，防篡改）
"""
import time
from urllib.parse import urlencode

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, RedirectResponse

from app.config import settings
from app.core.exceptions import ErrorCode
from app.core.rbac import get_current_user, permissions_of
from app.core.responses import fail, ok
from app.core.security import make_token
from app.schemas.requests import (LoginRequest, OidcMockAuthorizeRequest, TotpCodeRequest)
from app.services import (audit_chain, ldap_auth, oidc, password_policy, totp, user_store)

router = APIRouter()


def _login_payload(user: dict) -> dict:
    return {
        "token": make_token(user["username"], user["role"]),
        "username": user["username"],
        "name": user.get("name") or user["username"],
        "role": user["role"],
        "permissions": sorted(permissions_of(user["role"])),
        "totp_enabled": bool(user.get("totp_enabled")),
    }


def _audit_login(username: str, mode: str, ok_: bool, reason: str = "") -> None:
    try:
        audit_chain.append({"type": "login", "username": username, "mode": mode, "ok": ok_,
                            "reason": reason, "time": time.strftime("%Y-%m-%d %H:%M:%S")})
    except Exception:
        pass


@router.post("/login")
def login(body: LoginRequest):
    if not body.username or not body.password:
        return fail(ErrorCode.PARAM_INVALID, "请输入账号与密码", 400)
    remaining = password_policy.locked_remaining(body.username)
    if remaining:
        return fail(ErrorCode.RATE_LIMITED,
                    f"连续登录失败次数过多，账号已锁定，请约 {max(1, remaining // 60)} 分钟后重试", 429)

    if body.mode == "ldap":
        res = ldap_auth.authenticate(body.username, body.password)
        if res.get("error"):
            password_policy.record_fail(body.username)
            _audit_login(body.username, "ldap", False, res["error"])
            return fail(ErrorCode.UNAUTHORIZED, res["error"], 401)
        user = res["user"]
    else:
        user = user_store.authenticate(body.username, body.password)
        if not user:
            password_policy.record_fail(body.username)
            _audit_login(body.username, "local", False, "账号或密码错误")
            return fail(ErrorCode.UNAUTHORIZED, "账号或密码错误", 401)

    if user["status"] != "active":
        return fail(ErrorCode.FORBIDDEN, "账号已被禁用，请联系管理员", 403)

    secret = user.get("totp_secret") if user.get("totp_enabled") else None
    if secret and not totp.verify(secret, body.totp_code):
        password_policy.record_fail(body.username)
        _audit_login(body.username, body.mode, False, "TOTP 口令不正确")
        return fail(ErrorCode.PARAM_INVALID, "动态口令（TOTP）不正确", 401)

    password_policy.reset(body.username)
    _audit_login(user["username"], body.mode, True)
    return ok(_login_payload(user), "登录成功")


# ---------------- TOTP 双因素（等保：身份鉴别-双因素） ----------------

@router.post("/totp/setup", dependencies=[Depends(get_current_user)])
def totp_setup(user: dict = Depends(get_current_user)):
    """生成 TOTP 密钥与 otpauth:// URI（此时未启用；扫码后调 /totp/enable 确认）"""
    if user.get("totp_enabled"):
        return fail(ErrorCode.PARAM_INVALID, "双因素已启用，如需更换请先关闭", 400)
    secret = totp.generate_secret()
    user_store.set_totp(user["username"], secret, enabled=False)
    return ok({"secret": secret, "otpauth_uri": totp.otpauth_uri(user["username"], secret),
               "digits": 6, "period": 30},
              "已生成密钥，请用 authenticator 扫码后提交动态口令完成启用")


@router.post("/totp/enable", dependencies=[Depends(get_current_user)])
def totp_enable(body: TotpCodeRequest, user: dict = Depends(get_current_user)):
    full = user_store.get(user["username"]) or {}
    secret = full.get("totp_secret")
    if not secret:
        return fail(ErrorCode.PARAM_INVALID, "请先调用 /auth/totp/setup 生成密钥", 400)
    if not totp.verify(secret, body.code):
        return fail(ErrorCode.PARAM_INVALID, "动态口令不正确，请重试", 401)
    user_store.set_totp(user["username"], secret, enabled=True)
    return ok({"totp_enabled": True}, "双因素认证已启用，下次登录需输入动态口令")


@router.post("/totp/disable", dependencies=[Depends(get_current_user)])
def totp_disable(user: dict = Depends(get_current_user)):
    user_store.set_totp(user["username"], None, enabled=False)
    return ok({"totp_enabled": False}, "双因素认证已关闭")


# ---------------- OIDC 单点登录 ----------------

@router.get("/oidc/status")
def oidc_status():
    return ok(oidc.status())


@router.get("/oidc/login")
def oidc_login(username: str = "admin"):
    """302 到 IdP authorize；mock IdP 模式下指定 username 直接进入授权"""
    state = oidc.make_state()
    if settings.OIDC_MOCK:
        base = settings.OIDC_ISSUER.rstrip("/")
        url = f"{base}/authorize?{urlencode({
            'response_type': 'code', 'client_id': settings.OIDC_CLIENT_ID,
            'redirect_uri': settings.OIDC_REDIRECT_URI, 'scope': settings.OIDC_SCOPES,
            'state': state, 'username': username,
        })}"
        return RedirectResponse(url, status_code=302)
    if not oidc.enabled():
        return fail(ErrorCode.PARAM_INVALID, oidc.status()["hint"], 400)
    return RedirectResponse(oidc.authorize_url(state), status_code=302)


@router.get("/oidc/callback")
def oidc_callback(code: str = "", state: str = ""):
    if not code or not state:
        return fail(ErrorCode.PARAM_INVALID, "缺少 code / state", 400)
    if not oidc.check_state(state):
        return fail(ErrorCode.PARAM_INVALID, "state 无效或已过期（防 CSRF 校验失败）", 400)
    if not oidc.enabled() and not settings.OIDC_MOCK:
        return fail(ErrorCode.PARAM_INVALID, oidc.status()["hint"], 400)
    try:
        claims = oidc.exchange_code(code)
    except Exception as e:
        return fail(ErrorCode.UNAUTHORIZED, f"OIDC 令牌交换失败：{type(e).__name__}", 401)
    user, msg = oidc.map_user(claims)
    if not user:
        return fail(ErrorCode.FORBIDDEN, msg, 403)
    _audit_login(user["username"], "oidc", True, msg)
    return ok(_login_payload(user), f"OIDC 登录成功{'（' + msg + '）' if msg else ''}")


# ---------------- 内置 mock IdP（仅 OIDC_MOCK=true，本地端到端验证用） ----------------

@router.get("/oidc/mock/authorize")
def oidc_mock_authorize(username: str = "admin", redirect_uri: str = "", state: str = ""):
    """模拟 IdP 授权页：直接签发授权码并 302 回 redirect_uri?code&state"""
    if not settings.OIDC_MOCK:
        return fail(ErrorCode.FORBIDDEN, "mock IdP 未启用（OIDC_MOCK=false）", 403)
    if not user_store.get(username):
        return fail(ErrorCode.NOT_FOUND, f"本地不存在用户 {username}", 404)
    code = oidc.mock_issue_code(username)
    params = urlencode({"code": code, "state": state})
    return RedirectResponse(f"{redirect_uri or settings.OIDC_REDIRECT_URI}?{params}", status_code=302)


@router.post("/oidc/mock/token")
def oidc_mock_token(code: str = ""):
    """模拟 IdP 的 token 端点：按 OAuth 规范返回**裸 JSON**（id_token 不套业务信封）"""
    if not settings.OIDC_MOCK:
        return fail(ErrorCode.FORBIDDEN, "mock IdP 未启用", 403)
    try:
        return JSONResponse(oidc.mock_token(code))
    except ValueError as e:
        return fail(ErrorCode.PARAM_INVALID, str(e), 400)
