"""统一响应格式（对齐技术方案 5.1）：
{ "code": 0, "msg": "success", "data": {}, "trace_id": "xxx" }
"""
from typing import Any, Optional

from fastapi.responses import JSONResponse

from app.core.middleware import get_trace_id


def ok(data: Any = None, msg: str = "success") -> dict:
    return {"code": 0, "msg": msg, "data": data, "trace_id": get_trace_id()}


def fail(code: int, msg: str, http_status: int = 200, data: Optional[Any] = None) -> JSONResponse:
    """错误响应：非 0 code 必须携带 trace_id（技术方案 5.4）"""
    return JSONResponse(
        status_code=http_status,
        content={"code": code, "msg": msg, "data": data, "trace_id": get_trace_id()},
    )
