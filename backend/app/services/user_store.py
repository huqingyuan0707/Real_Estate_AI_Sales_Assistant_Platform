"""用户存储（RBAC）：data/users.json 持久化，首次启动自动播种演示账号。

角色：admin 管理员 / manager 主管 / member 成员（权限矩阵见 core/rbac.py）。
生产迁移 users 表（bcrypt 密码列 + 角色外键），本模块对外接口保持不变。
"""
import json
import os
import threading
import time
from typing import Optional

from app.core.security import hash_password

_LOCK = threading.Lock()
# backend/app/services/user_store.py → parents[2] = backend
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
_PATH = os.path.join(_DATA_DIR, "users.json")

_SEED = [
    {"username": "admin", "name": "演示管理员", "password": "123456", "role": "admin", "workspace": "信息技术部", "status": "active"},
    {"username": "wangmin", "name": "王敏", "password": "123456", "role": "manager", "workspace": "营销一部", "status": "active"},
    {"username": "liqiang", "name": "李强", "password": "123456", "role": "member", "workspace": "营销一部", "status": "active"},
    {"username": "zhangwei", "name": "张伟", "password": "123456", "role": "member", "workspace": "营销二部", "status": "active"},
]

VALID_ROLES = ("admin", "manager", "member")


def _load() -> list[dict]:
    try:
        with open(_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save(users: list[dict]) -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_PATH, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def ensure_seed() -> None:
    """文件不存在或为空时播种演示账号（幂等）"""
    with _LOCK:
        users = _load()
        if not users:
            _save([
                {**u, "password_hash": hash_password(u.pop("password")), "created_at": time.strftime("%Y-%m-%d %H:%M")}
                for u in _SEED
            ])


def _public(u: dict) -> dict:
    return {k: u[k] for k in ("username", "name", "role", "workspace", "status", "created_at") if k in u}


def authenticate(username: str, password: str) -> Optional[dict]:
    with _LOCK:
        for u in _load():
            if u["username"] == username and u["password_hash"] == hash_password(password):
                return u
    return None


def get(username: str) -> Optional[dict]:
    with _LOCK:
        return next((u for u in _load() if u["username"] == username), None)


def list_users() -> list[dict]:
    with _LOCK:
        return [_public(u) for u in _load()]


def create_user(name: str, username: str, password: str, role: str, workspace: str) -> dict:
    if role not in VALID_ROLES:
        raise ValueError(f"非法角色：{role}")
    with _LOCK:
        users = _load()
        if any(u["username"] == username for u in users):
            raise ValueError(f"账号 {username} 已存在")
        user = {
            "username": username, "name": name, "password_hash": hash_password(password),
            "role": role, "workspace": workspace, "status": "active",
            "created_at": time.strftime("%Y-%m-%d %H:%M"),
        }
        users.append(user)
        _save(users)
        return _public(user)


def update_user(username: str, *, role: Optional[str] = None, status: Optional[str] = None,
                name: Optional[str] = None, workspace: Optional[str] = None,
                reset_password: bool = False) -> dict:
    """管理员调整用户：角色 / 启停 / 资料 / 重置密码为 123456"""
    if role is not None and role not in VALID_ROLES:
        raise ValueError(f"非法角色：{role}")
    with _LOCK:
        users = _load()
        user = next((u for u in users if u["username"] == username), None)
        if not user:
            raise ValueError(f"用户 {username} 不存在")
        # 防锁死：不允许禁用自己 / 把唯一管理员降级
        if username == "admin" and (status == "disabled" or (role is not None and role != "admin")):
            raise ValueError("不允许停用或降级内置管理员账号")
        if role is not None:
            user["role"] = role
        if status is not None:
            user["status"] = status
        if name is not None:
            user["name"] = name
        if workspace is not None:
            user["workspace"] = workspace
        if reset_password:
            user["password_hash"] = hash_password("123456")
        _save(users)
        return _public(user)


def set_totp(username: str, secret: str | None, enabled: bool) -> dict:
    """设置 / 关闭 TOTP 双因素（secret=None 表示解绑）"""
    with _LOCK:
        users = _load()
        user = next((u for u in users if u["username"] == username), None)
        if not user:
            raise ValueError(f"用户 {username} 不存在")
        if secret is None:
            user.pop("totp_secret", None)
            user["totp_enabled"] = False
        else:
            user["totp_secret"] = secret
            user["totp_enabled"] = enabled
        _save(users)
        return {"username": username, "totp_enabled": user.get("totp_enabled", False)}


def delete_user(username: str) -> None:
    if username == "admin":
        raise ValueError("不允许删除内置管理员账号")
    with _LOCK:
        users = _load()
        rest = [u for u in users if u["username"] != username]
        if len(rest) == len(users):
            raise ValueError(f"用户 {username} 不存在")
        _save(rest)


ensure_seed()
