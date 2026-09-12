"""认证安全层（演示平台轻量实现，零第三方依赖）

- 密码存储：sha256(salt:password) 十六进制
- Token：base64url(payload) + "." + HMAC-SHA256 签名，无状态可校验；
  payload 含 username/role/exp。生产建议迁移 PyJWT + 服务端吊销列表。
"""
import base64
import hashlib
import hmac
import json
import time

from app.config import settings

_PASSWORD_SALT = "reai"


def hash_password(password: str) -> str:
    return hashlib.sha256(f"{_PASSWORD_SALT}:{password}".encode()).hexdigest()


def _sign(data: bytes) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), data, hashlib.sha256).hexdigest()


def make_token(username: str, role: str) -> str:
    """签发访问令牌：payload.exp = now + TOKEN_EXPIRE_HOURS"""
    payload = {
        "username": username,
        "role": role,
        "exp": int(time.time()) + settings.TOKEN_EXPIRE_HOURS * 3600,
    }
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"{raw}.{_sign(raw.encode())}"


def parse_token(token: str) -> dict | None:
    """校验签名与有效期，有效返回 payload，否则 None"""
    try:
        raw, sig = token.rsplit(".", 1)
        if not hmac.compare_digest(_sign(raw.encode()), sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None
