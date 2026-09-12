"""TOTP 动态口令（RFC 6238 纯 Python 实现，零第三方依赖）

等保三级「身份鉴别：双因素认证」——静态密码（第一因素）+ TOTP（第二因素）。
流程：POST /auth/totp/setup 生成密钥与 otpauth:// URI（ authenticator 扫码）
→ POST /auth/totp/enable {code} 校验通过后启用 → 登录时必须携带动态口令。
"""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

_STEP = 30          # 时间步长（秒）
_DIGITS = 6


def generate_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** _DIGITS)
    return f"{value:0{_DIGITS}d}"


def verify(secret: str, code: str, window: int = 1) -> bool:
    """校验动态口令（±1 个时间步长容差）；constant-time 比较"""
    if not secret or not (code or "").strip().isdigit():
        return False
    counter = int(time.time()) // _STEP
    target = code.strip()
    return any(hmac.compare_digest(_code(secret, counter + off), target)
               for off in range(-window, window + 1))


def otpauth_uri(username: str, secret: str) -> str:
    """authenticator 扫码用 URI"""
    return (f"otpauth://totp/RealEstateAI:{quote(username)}"
            f"?secret={secret}&issuer=RealEstateAI&digits={_DIGITS}&period={_STEP}")
