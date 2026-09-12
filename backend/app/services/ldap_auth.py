"""LDAP 目录认证（对齐企业级 RAG 文档第六节：认证 LDAP）

职责边界：LDAP **只做身份鉴别**（绑定校验）；授权仍以本地 users.json 的角色为准，
因此管理员需先在本地创建同名账号。未配置 / 未安装依赖时返回明确指引，不阻塞本地登录。

配置：LDAP_URI（如 ldap://dc.corp.local:389）、LDAP_BASE_DN、LDAP_USER_TEMPLATE（绑定 DN 模板）。
"""
from app.config import settings
from app.services import user_store


def status() -> dict:
    return {
        "ldap_enabled": bool(settings.LDAP_URI and settings.LDAP_BASE_DN),
        "uri": settings.LDAP_URI or "",
        "base_dn": settings.LDAP_BASE_DN or "",
        "user_template": settings.LDAP_USER_TEMPLATE if settings.LDAP_URI else "",
    }


def authenticate(username: str, password: str) -> dict:
    """LDAP 绑定校验。返回 {"user": 本地用户} 或 {"error": 提示}"""
    if not settings.LDAP_URI or not settings.LDAP_BASE_DN:
        return {"error": "LDAP 未配置（LDAP_URI / LDAP_BASE_DN），请使用本地账号密码登录"}
    try:
        import ldap3
    except ImportError:
        return {"error": "服务端未安装 ldap3（pip install ldap3），LDAP 登录暂不可用"}

    dn = settings.LDAP_USER_TEMPLATE.format(username=username, base_dn=settings.LDAP_BASE_DN)
    try:
        server = ldap3.Server(settings.LDAP_URI, connect_timeout=3, get_info=None)
        conn = ldap3.Connection(server, user=dn, password=password, auto_bind=True,
                                receive_timeout=5)
        conn.unbind()
    except Exception as e:
        return {"error": f"LDAP 鉴权失败：{type(e).__name__}（请检查域账号密码或目录服务状态）"}

    user = user_store.get(username)
    if not user:
        return {"error": f"LDAP 鉴权通过，但本地不存在账号 {username}，请联系管理员创建后再登录"}
    return {"user": user, "dn": dn}
