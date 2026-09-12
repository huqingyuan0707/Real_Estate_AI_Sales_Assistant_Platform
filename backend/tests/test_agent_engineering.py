"""Agent 工程化最小闭环测试：状态机/注册中心/执行器/Runtime/幂等/检查点。"""
import pytest

from app.modules.agent.policy.engine import PolicyEngine
from app.modules.agent.runtime import AgentRuntime
from app.modules.agent.state import AgentAction, AgentPhase, AgentState
from app.modules.agent.tools.executor import ToolExecutor
from app.modules.agent.tools.registry import ToolRegistry


def test_state_checkpoint_restore():
    s = AgentState(query="q", trace_id="t")
    s.finish("ok")
    assert s.done and s.phase == AgentPhase.DONE
    assert AgentState.restore(s.checkpoint()).answer == "ok"


def test_registry_scopes():
    reg = ToolRegistry()
    reg.register("demo.tool", {"type": "object"}, lambda: "hi", scopes=["kb"])
    assert reg.list_for_user({"role": "admin"})
    assert reg.list_for_user({"role": "member"}) == []  # member 无 kb 权限


@pytest.mark.asyncio
async def test_runtime_min_loop_no_llm():
    async def fake_tool(**kwargs):
        return {"answer": "fake-hit"}

    reg = ToolRegistry()
    reg.register("knowledge.search", {"type": "object"}, fake_tool)
    state = await AgentRuntime(
        tool_executor=ToolExecutor(registry=reg), policy=PolicyEngine(registry=reg),
    ).run("test")
    assert state.phase == AgentPhase.DONE and "fake-hit" in state.answer


@pytest.mark.asyncio
async def test_executor_idempotent_and_forbidden():
    calls = {"n": 0}

    async def h(**kw):
        calls["n"] += 1
        return {"ok": True}

    reg = ToolRegistry()
    reg.register("t.once", {"type": "object"}, h, idempotent=True)
    reg.register("t.secret", {"type": "object"}, h, scopes=["kb"])
    exe = ToolExecutor(registry=reg)
    a = AgentAction(type="tool", name="t.once", args={}, idempotency_key="k1")
    await exe.execute(a, {"role": "member", "username": "u"})
    await exe.execute(a, {"role": "member", "username": "u"})
    assert calls["n"] == 1  # 幂等命中
    with pytest.raises(PermissionError):
        await exe.execute(AgentAction(type="tool", name="t.secret", args={}),
                          {"role": "member", "username": "u"})


@pytest.mark.asyncio
async def test_policy_approval_branch():
    reg = ToolRegistry()
    reg.register("send_email", {"type": "object"}, lambda **k: {}, needs_approval=True)
    eng = PolicyEngine(registry=reg)
    assert await eng.check(AgentAction(type="tool", name="send_email", args={}),
                           {"role": "admin"}) == "approval"

    class _ApprovalPlanner:
        async def next(self, state):
            return AgentAction(type="tool", name="send_email", args={"to": "a@b.c"})

    state = await AgentRuntime(
        planner=_ApprovalPlanner(), tool_executor=ToolExecutor(registry=reg),
        policy=eng).run("send email please")
    # 审批工具 → WAITING_APPROVAL 暂停
    assert state.phase == AgentPhase.WAITING_APPROVAL
