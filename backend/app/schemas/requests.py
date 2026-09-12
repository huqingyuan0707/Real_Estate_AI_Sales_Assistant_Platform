"""请求体 Pydantic 模型（设计阶段仅覆盖页面交互所需的最小字段集）"""
from typing import Literal, Optional

from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str
    mode: Literal["local", "ldap"] = "local"
    totp_code: str = ""                      # TOTP 动态口令（启用双因素后必填）


class TotpCodeRequest(BaseModel):
    code: str


class OidcMockAuthorizeRequest(BaseModel):
    """开发用 mock IdP：为指定本地用户签发授权码（仅 OIDC_MOCK=true 时可用）"""
    username: str


class ChatRequest(BaseModel):
    thread_id: Optional[str] = None
    content: str
    skill: Optional[str] = None          # @技能 名称
    attachments: Optional[list[str]] = None  # 附件文件名
    tenant_id: str = "default"           # 租户隔离
    user_id: str = "admin"               # 用户隔离


class MemoryCreateRequest(BaseModel):
    """写入长期记忆：未授权进入 pending；敏感信息必须设置过期时间"""
    content: str
    category: Optional[str] = None       # preference / project / fact
    authorized: bool = False             # 用户明确授权
    expires_days: Optional[int] = None   # 过期天数（敏感信息必填）
    tenant_id: str = "default"
    user_id: str = "admin"


class MemoryUpdateRequest(BaseModel):
    content: Optional[str] = None
    category: Optional[str] = None
    authorized: Optional[bool] = None    # 传 true 即为授权确认
    expires_days: Optional[int] = None
    tenant_id: str = "default"
    user_id: str = "admin"


class DocumentSearchRequest(BaseModel):
    query: str
    top_k: int = 5


class HouseConfirmRequest(BaseModel):
    """HITL 人工确认/修正提交（对应 /house/parse/{task_id}/confirm）"""
    house_struct: dict


class SkillInvokeRequest(BaseModel):
    """Skill 调用输入（对应 /skills/{id}/invoke）"""
    input: str
    tenant_id: str = "default"
    user_id: str = "admin"


class ResumeRequest(BaseModel):
    """断点续聊恢复输入（对应 /sessions/{thread_id}/resume）"""
    content: str
    tenant_id: str = "default"
    user_id: str = "admin"


class DocReviewRequest(BaseModel):
    """知识审核动作：approve 发布 / reject 打回草稿 / archive 归档"""
    action: Literal["approve", "reject", "archive"]
    comment: str = ""


class IndexRebuildRequest(BaseModel):
    """换嵌入模型重建索引（embed_model 省略 = 用当前模型重建）"""
    embed_model: Optional[str] = None


class IndexRollbackRequest(BaseModel):
    """回滚到指定索引快照"""
    backup: str


class UserCreateRequest(BaseModel):
    username: str
    display_name: str
    role: Literal["admin", "manager", "member"] = "member"
    workspace: str
    initial_password: str


class UserUpdateRequest(BaseModel):
    """管理员调整用户：角色 / 启停 / 重置密码"""
    role: Optional[Literal["admin", "manager", "member"]] = None
    status: Optional[Literal["active", "disabled"]] = None
    reset_password: bool = False
