"""RBAC 权限设计（技术方案：用户-角色-权限，接口级校验）

权限码按页面/操作粒度划分，角色映射：
- admin   管理员：全部权限
- manager 主管：业务全量 + 知识库 + 审计/费用查看，无用户管理与系统设置
- member  成员：日常业务（对话/空间引擎/Skill/任务/记忆）

使用方式：
- 认证：Depends(get_current_user)          → 未登录 401 / 1002
- 鉴权：Depends(require_perm("kb"))        → 无权限 403 / 1003
路由级批量保护见 api/v1/router.py（include_router dependencies）。
"""
from typing import Callable

from fastapi import Depends, Header, HTTPException

from app.core.exceptions import ErrorCode
from app.core.security import parse_token
from app.core.user_context import set_current_user
from app.services import user_store

# 权限码
PERM_CHAT = "chat"                # 智能对话
PERM_HOUSE = "house"              # 空间智能引擎（户型解析/装修图入口）
PERM_RENDER = "render"            # AI 一键装修图生成
PERM_SKILL = "skill"              # Skill 市场
PERM_TASK = "task"                # 任务中心
PERM_MEMORY = "memory"            # 记忆管理
PERM_KB = "kb"                    # 知识库管理（上传/删除/试搜）
PERM_COST = "cost"                # 费用看板
PERM_AUDIT = "audit"              # 审计日志
PERM_USER_MANAGE = "user_manage"  # 用户管理
PERM_SETTINGS = "settings"        # 系统设置

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {PERM_CHAT, PERM_HOUSE, PERM_RENDER, PERM_SKILL, PERM_TASK, PERM_MEMORY,
              PERM_KB, PERM_COST, PERM_AUDIT, PERM_USER_MANAGE, PERM_SETTINGS},
    "manager": {PERM_CHAT, PERM_HOUSE, PERM_RENDER, PERM_SKILL, PERM_TASK, PERM_MEMORY,
                PERM_KB, PERM_COST, PERM_AUDIT},
    "member": {PERM_CHAT, PERM_HOUSE, PERM_RENDER, PERM_SKILL, PERM_TASK, PERM_MEMORY},
}

ROLE_NAMES = {"admin": "管理员", "manager": "主管", "member": "成员"}


def permissions_of(role: str) -> set[str]:
    return ROLE_PERMISSIONS.get(role, set())


def _auth_error(http_status: int, code: int, msg: str) -> HTTPException:
    # detail 携带业务错误码，前端按 code 分流（1002 重新登录 / 1003 提示无权限）
    return HTTPException(status_code=http_status, detail={"code": code, "msg": msg})


async def get_current_user(authorization: str = Header(default="")) -> dict:
    """从 Authorization: Bearer <token> 解析当前用户（users.json 实时校验状态）

    声明为 async：ContextVar（当前用户）必须在请求所属 task 内写入才能被服务层读到，
    同步依赖会跑在线程池、上下文无法传回（services/ai_config 按用户取 AI Key 依赖此机制）。
    """
    if not authorization.startswith("Bearer "):
        raise _auth_error(401, ErrorCode.UNAUTHORIZED, "未登录或 Token 缺失")
    payload = parse_token(authorization[7:].strip())
    user = user_store.get(payload["username"]) if payload else None
    if not user or user["status"] != "active":
        raise _auth_error(401, ErrorCode.UNAUTHORIZED, "登录状态无效或已过期，请重新登录")
    set_current_user(user["username"])
    return user


def require_perm(*perms: str) -> Callable:
    """依赖工厂：当前用户必须拥有全部给定权限码"""
    def dep(user: dict = Depends(get_current_user)) -> dict:
        if not set(perms) <= permissions_of(user["role"]):
            raise _auth_error(403, ErrorCode.FORBIDDEN, "权限不足（RBAC）")
        return user
    return dep
