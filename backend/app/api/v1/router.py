"""v1 路由聚合（含 RBAC 路由级保护）

- auth：公开（登录入口）
- 业务路由：Depends(get_current_user) 登录即可
- 管理路由（settings/cost/audit/users）：require_perm 对应权限码
- documents：路由级登录，上传/删除端点级 kb 权限（见 documents.py）
"""
from fastapi import APIRouter, Depends

from app.api.v1.endpoints import (admin, agent, ai_config, audit, auth, chat, compliance, cost, documents,
                                   feedback, furniture, house, index_admin, knowledge, memory, render,
                                   sessions, settings, skills, tasks, tools, users)
from app.core.rbac import get_current_user, require_perm

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["认证"])

_login = [Depends(get_current_user)]
# 我的 AI 服务配置：登录即可（每人在前端填自己的 Key，不受 settings 权限限制）
api_router.include_router(ai_config.router, prefix="/ai-config", dependencies=_login, tags=["我的AI配置"])
api_router.include_router(chat.router, prefix="/chat", dependencies=_login, tags=["对话"])
api_router.include_router(sessions.router, prefix="/sessions", dependencies=_login, tags=["会话"])
api_router.include_router(documents.router, prefix="/documents", dependencies=_login, tags=["知识库"])
# 索引管理（版本 / 换模型重建 / 快照回滚）：端点内用 require_perm("kb") 保护
api_router.include_router(index_admin.router, prefix="/index-admin", dependencies=_login, tags=["索引管理"])
api_router.include_router(skills.router, prefix="/skills", dependencies=_login, tags=["Skill市场"])
api_router.include_router(house.router, prefix="/house", dependencies=_login, tags=["户型解析"])
api_router.include_router(furniture.router, prefix="/furniture", dependencies=_login, tags=["业主家具清单"])
# render：路由级不挂统一依赖，在端点级区分——任务/历史接口需登录，成图文件端点开放
# （浏览器 <img>/window.open 无法携带 Authorization；文件名 128 位 UUID 不可枚举）
api_router.include_router(render.router, prefix="/render", tags=["一键装修图"])
api_router.include_router(memory.router, prefix="/memory", dependencies=_login, tags=["记忆管理"])
# 反馈闭环：提交反馈登录即可；运营统计端点内用 require_perm("kb") 保护
api_router.include_router(feedback.router, prefix="/feedback", dependencies=_login, tags=["反馈闭环"])
api_router.include_router(tasks.router, prefix="/tasks", dependencies=_login, tags=["任务中心"])
api_router.include_router(tasks.router, prefix="/task", dependencies=_login, tags=["异步任务(文档路径)"])
# Agent 工程化：Runtime/工具/RAG/审批/评估统一门面（登录即可，管理端点内再做权限校验）
api_router.include_router(agent.router, dependencies=_login)
api_router.include_router(tools.router, dependencies=_login)
api_router.include_router(knowledge.router, dependencies=_login)
api_router.include_router(admin.router, dependencies=_login)

api_router.include_router(settings.router, prefix="/settings", dependencies=[Depends(require_perm("settings"))], tags=["系统设置"])
api_router.include_router(cost.router, prefix="/cost", dependencies=[Depends(require_perm("cost"))], tags=["费用统计"])
api_router.include_router(audit.router, prefix="/audit", dependencies=[Depends(require_perm("audit"))], tags=["审计日志"])
api_router.include_router(users.router, prefix="/users", dependencies=[Depends(require_perm("user_manage"))], tags=["用户管理"])
# 合规自查报表（等保三级控制点对照）：端点内 require_perm("audit") 保护
api_router.include_router(compliance.router, prefix="/compliance", dependencies=_login, tags=["合规"])
