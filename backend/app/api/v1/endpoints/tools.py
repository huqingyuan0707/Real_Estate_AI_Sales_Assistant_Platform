"""工具注册中心对外端点：列表（按权限过滤）/ 调用（幂等）。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.rbac import get_current_user
from app.core.responses import ok
from app.modules.agent.state import AgentAction
from app.modules.agent.tools.executor import ToolExecutor
from app.modules.agent.tools.registry import registry

router = APIRouter(tags=["tools"])
_executor = ToolExecutor()


class ToolCallBody(BaseModel):
    args: dict = {}
    idempotency_key: str | None = None


@router.get("/tools")
async def list_tools(user=Depends(get_current_user)):
    return ok(registry.list_for_user(user))


@router.post("/tools/{name}/invoke")
async def invoke_tool(name: str, body: ToolCallBody, user=Depends(get_current_user)):
    action = AgentAction(type="tool", name=name, args=body.args,
                         idempotency_key=body.idempotency_key)
    return ok(await _executor.execute(action, user))
