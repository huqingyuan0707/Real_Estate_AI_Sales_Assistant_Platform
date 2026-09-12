"""FastAPI 依赖注入装配（Router → Service → Runtime 薄装配层）。

Router 只做参数校验/鉴权/调用 Service，此处提供 Service 单例工厂，
避免在 Router 内直接 new 重依赖。全部懒加载，防止循环导入。
"""
from fastapi import Depends

from app.core.rbac import get_current_user  # noqa: F401  (统一鉴权出口复用)


def get_agent_service():
    """AgentService 单例工厂（懒导入，避免循环依赖）。"""
    from app.modules.agent.service import get_agent_service_singleton

    return get_agent_service_singleton()


def get_current_user_dep(user=Depends(get_current_user)):
    return user
