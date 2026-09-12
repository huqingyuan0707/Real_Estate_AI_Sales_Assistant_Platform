"""应用生命周期事件（startup/shutdown），供 main.py 注册。"""
from app.core.logging import log_event


async def on_startup() -> None:
    log_event("app.startup")


async def on_shutdown() -> None:
    log_event("app.shutdown")
