"""用户管理接口（RBAC：user_manage 权限，路由级注入，数据源 user_store）"""
from fastapi import APIRouter

from app.core.exceptions import ErrorCode
from app.core.responses import fail, ok
from app.mock_data import WORKSPACES
from app.schemas.requests import UserCreateRequest, UserUpdateRequest
from app.services import password_policy, user_store

router = APIRouter()


@router.get("")
def list_users():
    return ok({"users": user_store.list_users(), "workspaces": WORKSPACES, "roles": list(user_store.VALID_ROLES)})


@router.post("")
def create_user(body: UserCreateRequest):
    # 密码策略（等保：身份鉴别）：长度 + 大小写 + 数字
    issues = password_policy.validate(body.initial_password)
    if issues:
        return fail(ErrorCode.PARAM_INVALID, "密码不满足策略：" + "；".join(issues), 400)
    try:
        user = user_store.create_user(
            name=body.display_name, username=body.username,
            password=body.initial_password, role=body.role, workspace=body.workspace,
        )
    except ValueError as e:
        return fail(ErrorCode.PARAM_INVALID, str(e), 400)
    return ok(user, "用户已创建")


@router.put("/{username}")
def update_user(username: str, body: UserUpdateRequest):
    try:
        user = user_store.update_user(
            username, role=body.role, status=body.status, reset_password=body.reset_password,
        )
    except ValueError as e:
        return fail(ErrorCode.PARAM_INVALID, str(e), 400)
    return ok(user, "用户已更新")


@router.delete("/{username}")
def delete_user(username: str):
    try:
        user_store.delete_user(username)
    except ValueError as e:
        return fail(ErrorCode.PARAM_INVALID, str(e), 400)
    return ok({"username": username}, "用户已删除")


@router.get("/workspaces")
def list_workspaces():
    return ok(WORKSPACES)
