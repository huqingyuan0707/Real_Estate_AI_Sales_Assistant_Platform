"""审计门面：复用现有 audit_chain/services，保证 agent 链路调用不断。"""
import asyncio


async def log(user_id: str, action: str, trace_id: str = "", detail: dict | None = None) -> None:
    for mod_name, fn_name in (("app.services.audit_chain", "append"),
                              ("app.services.governance", "audit"),
                              ("app.services.observability", "record")):
        try:
            mod = __import__(mod_name, fromlist=[fn_name])
            fn = getattr(mod, fn_name, None)
            if fn is None:
                continue
            if asyncio.iscoroutinefunction(fn):
                await fn(user_id, action, trace_id, detail or {})
            else:
                await asyncio.to_thread(fn, user_id, action, trace_id, detail or {})
            return
        except Exception:
            continue
