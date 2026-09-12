"""审批流：敏感工具调用进入 WAITING_APPROVAL → approve/修改参数后 resume。"""
import uuid


class ApprovalService:
    def __init__(self):
        self._store: dict[str, dict] = {}

    async def request(self, action, user: dict | None, reason: str = "") -> dict:
        approval_id = uuid.uuid4().hex
        self._store[approval_id] = {
            "id": approval_id, "name": action.name, "args": dict(action.args),
            "user": (user or {}).get("username", "anonymous"), "reason": reason,
            "status": "pending",
        }
        try:
            from app.core.logging import log_event

            log_event("approval.request", approval_id=approval_id, action=action.name)
        except Exception:
            pass
        return self._store[approval_id]

    async def approve(self, approval_id: str, user: dict | None,
                      modified_args: dict | None = None):
        from app.modules.agent.policy.engine import PolicyEngine
        from app.modules.agent.state import AgentAction
        from app.modules.agent.tools.executor import ToolExecutor

        approval = self._store.get(approval_id)
        if not approval:
            raise KeyError("approval not found")
        await PolicyEngine().ensure_can_approve(user, approval)
        approval["status"] = "approved"
        action = AgentAction(name=approval["name"], args=modified_args or approval["args"])
        return await ToolExecutor().execute(action, user)

    async def reject(self, approval_id: str, user: dict | None, reason: str = "") -> dict:
        approval = self._store.get(approval_id)
        if not approval:
            raise KeyError("approval not found")
        approval["status"] = "rejected"
        approval["reject_reason"] = reason
        return approval
