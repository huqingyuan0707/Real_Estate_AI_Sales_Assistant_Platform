"""工具 Schema：每个工具必须有 JSON Schema + scope + 幂等声明。"""
from typing import Any, Callable

from pydantic import BaseModel


class ToolSpec(BaseModel):
    name: str
    description: str = ""
    parameters: dict[str, Any] = {}
    scopes: list[str] = []
    idempotent: bool = True
    needs_approval: bool = False

    model_config = {"arbitrary_types_allowed": True}
