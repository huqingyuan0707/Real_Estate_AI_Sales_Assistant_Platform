"""错误码规范（对齐技术方案 5.4，五位数分段：1xxxx 通用 / 2xxxx RAG对话 / 3xxxx 户型Skill / 5xxxx 系统）"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ErrorCode:
    OK = 0
    PARAM_INVALID = 1001          # 400 参数校验失败
    UNAUTHORIZED = 1002           # 401 未认证 / Token 过期
    FORBIDDEN = 1003              # 403 权限不足（RBAC）
    NOT_FOUND = 1004              # 404 资源不存在
    NETWORK_UNSTABLE = 1005       # 504 请求超时
    RAG_REJECT = 2001             # 422 知识库召回置信度不足（拒答）
    RATE_LIMITED = 2002           # 429 限流触发
    HOUSE_PARSE_FAILED = 3001     # 422 户型解析失败
    RULE_VALIDATE_FAILED = 3002   # 422 规则校验失败
    THIRD_PARTY_TIMEOUT = 3003    # 504 第三方 API 超时/失败
    TASK_CONFLICT = 4001          # 409 异步任务冲突（重复提交）
    TASK_EXPIRED = 4002           # 410 异步任务已过期（结果被清理）
    INTERNAL_ERROR = 5000         # 500 系统内部错误


_STATUS_TO_CODE = {
    400: ErrorCode.PARAM_INVALID, 401: ErrorCode.UNAUTHORIZED, 403: ErrorCode.FORBIDDEN,
    404: ErrorCode.NOT_FOUND, 409: ErrorCode.TASK_CONFLICT, 429: ErrorCode.RATE_LIMITED,
}


def _envelope(code: int, msg: str, trace_id: str = "-") -> dict:
    return {"code": code, "msg": msg, "data": None, "trace_id": trace_id}


def register_exception_handlers(app: FastAPI) -> None:
    """统一异常 → 统一信封（HTTP 状态保持，前端 401/403 分流不受影响）。"""
    from app.core.middleware import get_trace_id

    async def _http_exc(request: Request, exc: HTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail:
            code, msg = int(detail["code"]), str(detail.get("msg", ""))
        else:
            code = _STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL_ERROR)
            msg = detail if isinstance(detail, str) else f"请求失败（HTTP {exc.status_code}）"
        return JSONResponse(status_code=exc.status_code,
                            content=_envelope(code, msg, get_trace_id()))

    async def _validation_exc(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422,
                            content=_envelope(ErrorCode.PARAM_INVALID,
                                              f"参数校验失败：{exc.errors()[0]['msg']}" if exc.errors() else "参数校验失败",
                                              get_trace_id()))

    async def _unhandled(request: Request, exc: Exception):
        return JSONResponse(status_code=500,
                            content=_envelope(ErrorCode.INTERNAL_ERROR, "系统内部错误", get_trace_id()))

    app.add_exception_handler(HTTPException, _http_exc)
    app.add_exception_handler(RequestValidationError, _validation_exc)
    app.add_exception_handler(Exception, _unhandled)
