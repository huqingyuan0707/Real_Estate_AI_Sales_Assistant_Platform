"""编排器：多步骤/多智能体流程编排（P-E-V-S 风格的轻量实现）。

Runtime 负责单次 run 闭环；Orchestrator 负责把多个 Runtime/工具调用
组织成有向流程（顺序/分支/重试），并透传 trace_id。
"""
from app.modules.agent.state import AgentState


class Orchestrator:
    def __init__(self, runtime):
        self.runtime = runtime

    async def run_plan(self, steps: list[dict], user: dict | None = None,
                       trace_id: str | None = None) -> list[AgentState]:
        """steps: [{query, context, docs}] 顺序执行，失败即停并标记。"""
        results: list[AgentState] = []
        for s in steps:
            st = await self.runtime.run(
                query=s.get("query", ""), context=s.get("context"),
                docs=s.get("docs"), user=user, trace_id=trace_id,
            )
            results.append(st)
            if st.phase == "FAILED":
                break
        return results
