"""策略引擎：工具调用前置检查 → allow / deny / approval。"""
from app.modules.agent.tools.registry import registry


class PolicyEngine:
    async def check(self, action, user: dict | None = None) -> str:
        """返回 allow|approval；无权限直接抛 PermissionError。"""
        try:
            tool = registry.get(action.name)
        except KeyError:
            raise PermissionError(f"unknown tool: {action.name}")
        # scope 鉴权
        if tool["scopes"]:
            if user is None:
                raise PermissionError("login required")
            if user.get("role") != "admin":
                from app.core.rbac import permissions_of

                if not set(tool["scopes"]) <= permissions_of(user.get("role", "")):
                    raise PermissionError("tool not allowed")
        # 敏感动作 → 审批
        if tool.get("needs_approval"):
            return "approval"
        # 注入/越权启发式：危险关键词强制审批
        text = f"{action.name} {action.args}".lower()
        if any(k in text for k in ("delete", "drop", "payment", "transfer", "send_email", "rm -rf")):
            return "approval"
        return "allow"

    async def ensure_can_approve(self, user: dict | None, approval: dict) -> None:
        if not user or user.get("role") not in ("admin", "manager"):
            raise PermissionError("no approval permission")
