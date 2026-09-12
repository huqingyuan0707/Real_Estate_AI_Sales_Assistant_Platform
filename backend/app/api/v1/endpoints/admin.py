"""管理端点：健康 / 就绪 / 模型网关用量（治理视角）。"""
from fastapi import APIRouter, Depends

from app.core.rbac import get_current_user, require_perm
from app.core.responses import ok

router = APIRouter(tags=["admin"])


@router.get("/admin/health")
async def admin_health():
    return ok({"status": "ok"})


@router.get("/admin/ready")
async def admin_ready():
    checks = {"api": True}
    try:
        from app.services.llm import llm_available

        checks["llm"] = await llm_available()
    except Exception:
        checks["llm"] = False
    return ok(checks)


@router.get("/admin/usage")
async def admin_usage(user=Depends(require_perm("cost"))):
    from app.modules.agent.service import get_agent_service_singleton

    gw = get_agent_service_singleton().runtime.llm
    return ok(getattr(gw, "_usage", {}))
