"""Agent Service：业务编排层（厚 Service）。

装配 memory / rag / runtime / audit，对应文档 service.py：
load 上下文 → retrieve 知识 → runtime.run → audit 落库。
流式输出统一事件协议（text/tool_call/tool_result/approval/error/done）。
"""
import uuid

from app.core.middleware import get_trace_id
from app.modules.agent.runtime import AgentRuntime
from app.modules.agent.schemas import ChatRequest, StreamEvent


class AgentService:
    def __init__(self, runtime: AgentRuntime | None = None,
                 memory=None, rag=None, audit=None):
        self.runtime = runtime or AgentRuntime()
        self.memory = memory
        self.rag = rag
        self.audit = audit

    async def chat(self, payload: ChatRequest, user: dict | None = None) -> dict:
        trace_id = get_trace_id() or uuid.uuid4().hex[:16]
        context = await self._load_context(payload, user)
        docs = await self._retrieve(payload, user)
        state = await self.runtime.run(
            query=payload.query, context=context, docs=docs, user=user, trace_id=trace_id)
        await self._audit(user, "agent.chat", state.trace_id)
        return {"answer": state.answer, "trace_id": state.trace_id}

    async def stream_chat(self, payload: ChatRequest, user: dict | None = None):
        """async generator[StreamEvent]：供 SSE 端点消费。"""
        trace_id = get_trace_id() or uuid.uuid4().hex[:16]
        yield StreamEvent(type="text", content="🧠 规划中…", trace_id=trace_id)
        context = await self._load_context(payload, user)
        docs = await self._retrieve(payload, user)
        state = await self.runtime.run(
            query=payload.query, context=context, docs=docs, user=user, trace_id=trace_id)
        if state.phase == "WAITING_APPROVAL":
            yield StreamEvent(type="approval", action=(state.approval or {}).get("name"),
                              args=(state.approval or {}).get("args"), trace_id=trace_id)
        elif state.phase == "FAILED":
            yield StreamEvent(type="error", code="TOOL_FAILED",
                              message=state.error or "执行失败", trace_id=trace_id)
        else:
            yield StreamEvent(type="text", content=state.answer, trace_id=trace_id)
        await self._audit(user, "agent.chat", trace_id)
        yield StreamEvent(type="done", trace_id=trace_id)

    async def _load_context(self, payload: ChatRequest, user: dict | None):
        if self.memory is None or user is None:
            return None
        try:
            return await self.memory.load(payload.session_id, user.get("username", ""))
        except Exception:
            return None

    async def _retrieve(self, payload: ChatRequest, user: dict | None):
        if self.rag is None:
            return []
        try:
            return await self.rag.retrieve(payload.query, user)
        except Exception:
            return []

    async def _audit(self, user: dict | None, action: str, trace_id: str) -> None:
        if self.audit is None:
            return
        try:
            user_id = (user or {}).get("username", "anonymous")
            await self.audit.log(user_id, action, trace_id)
        except Exception:
            pass


_singleton: AgentService | None = None


def get_agent_service_singleton() -> AgentService:
    """进程级单例：装配现有 memory/rag/audit 适配器（懒导入防循环）。"""
    global _singleton
    if _singleton is not None:
        return _singleton
    from app.modules.agent.llm.gateway import ModelGateway
    from app.modules.agent.memory.service import MemoryService
    from app.modules.agent.policy.engine import PolicyEngine
    from app.modules.agent.rag.service import RagService

    memory = MemoryService()
    rag = RagService()
    policy = PolicyEngine()
    gateway = ModelGateway()
    runtime = AgentRuntime(policy=policy, memory=memory, llm=gateway)
    _singleton = AgentService(runtime=runtime, memory=memory, rag=rag, audit=None)
    return _singleton
