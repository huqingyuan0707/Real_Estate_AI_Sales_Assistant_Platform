"""结构化日志（request_id/trace_id/tenant_id/user_id 全链路透传）。"""
import json
import logging
import sys

from app.core.middleware import get_trace_id

_logger = logging.getLogger("agent-backend")
if not _logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(_handler)
_logger.setLevel(logging.INFO)


def get_logger(name: str = "agent-backend") -> logging.Logger:
    return logging.getLogger(name)


def log_event(event: str, level: int = logging.INFO, **fields) -> None:
    """输出一行 JSON 结构化日志，自动注入 trace_id。"""
    payload = {"event": event, "trace_id": get_trace_id(), **fields}
    _logger.log(level, json.dumps(payload, ensure_ascii=False, default=str))
