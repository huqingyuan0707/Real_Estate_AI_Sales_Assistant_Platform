"""工具注册中心：可插拔注册 + 按用户权限过滤。"""
from typing import Any, Callable


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, dict] = {}

    def register(self, name: str, schema: dict | None, handler: Callable,
                 scopes: list[str] | None = None, idempotent: bool = True,
                 needs_approval: bool = False, description: str = "") -> None:
        self._tools[name] = {
            "schema": schema or {}, "handler": handler, "scopes": scopes or [],
            "idempotent": idempotent, "needs_approval": needs_approval,
            "description": description, "name": name,
        }

    def get(self, name: str) -> dict:
        if name not in self._tools:
            raise KeyError(f"tool not found: {name}")
        return self._tools[name]

    def _allowed(self, tool: dict, user: dict | None) -> bool:
        if not tool["scopes"]:
            return True
        if user is None:
            return False
        role = user.get("role", "member")
        if role == "admin":
            return True
        from app.core.rbac import permissions_of

        return set(tool["scopes"]) <= permissions_of(role)

    def list_for_user(self, user: dict | None) -> list[dict]:
        return [
            {"name": t["name"], "description": t["description"],
             "parameters": t["schema"], "scopes": t["scopes"]}
            for t in self._tools.values() if self._allowed(t, user)
        ]


registry = ToolRegistry()


def _knowledge_search_handler(query: str, top_k: int = 5, **kwargs) -> dict:
    """内置知识检索工具（同步兜底版；异步路径由 RagService 覆盖时可替换）。"""
    try:
        from app.services import rag as rag_svc

        docs = rag_svc.retrieve(query, top_k=top_k) if hasattr(rag_svc, "retrieve") else []
        return {"answer": f"检索到 {len(docs)} 条", "docs": docs}
    except Exception as e:
        return {"answer": f"检索暂不可用：{e}", "docs": []}


registry.register(
    "knowledge.search",
    {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    _knowledge_search_handler,
    scopes=[], description="知识库检索（RAG）",
)
