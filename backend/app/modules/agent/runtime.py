"""Agent Runtime：Agent 的"操作系统"。Service 之下的核心执行层。

循环：PLANNING → ACTING(tool) → OBSERVING → REFLECTING → answer(DONE)，
敏感动作经策略引擎后进入 WAITING_APPROVAL。每步带 trace_id。
"""
import uuid

from app.modules.agent.state import AgentAction, AgentPhase, AgentState


class SimplePlanner:
    """最小规划器：首轮固定检索知识库工具，次轮基于观察生成答案。"""

    async def next(self, state: AgentState) -> AgentAction:
        if not state.observations:
            return AgentAction(type="tool", name="knowledge.search", args={"query": state.query})
        return AgentAction(type="answer")


class AgentRuntime:
    def __init__(self, planner=None, tool_executor=None, llm=None, policy=None, memory=None):
        from app.modules.agent.tools.executor import ToolExecutor

        self.planner = planner or SimplePlanner()
        self.tool_executor = tool_executor or ToolExecutor()
        self.llm = llm  # 可选：外部模型网关，未注入则用观察拼装答案
        self.policy = policy
        self.memory = memory

    async def run(self, query: str, context=None, docs=None, user: dict | None = None,
                  trace_id: str | None = None) -> AgentState:
        state = AgentState(query=query, user=user, context=context, docs=docs or [],
                           trace_id=trace_id or uuid.uuid4().hex[:16])
        state.phase = AgentPhase.PLANNING
        steps = 0
        while not state.done and steps < 6:
            steps += 1
            action = await self.planner.next(state)
            if action.type == "tool":
                state.phase = AgentPhase.ACTING
                if self.policy is not None:
                    verdict = await self.policy.check(action, user)
                    if verdict == "approval":
                        state.wait_approval(action)
                        break
                try:
                    result = await self.tool_executor.execute(action, user)
                except PermissionError as e:
                    state.fail(f"tool not allowed: {e}")
                    break
                except Exception as e:
                    state.fail(f"tool failed: {e}")
                    break
                state.observe(result)
                state.phase = AgentPhase.REFLECTING
            elif action.type == "answer":
                answer = await self._generate(state)
                state.finish(answer)
            elif action.type == "approval":
                state.wait_approval(action)
            else:
                state.fail(f"unknown action: {action.type}")
        return state

    async def _generate(self, state: AgentState) -> str:
        if self.llm is not None:
            try:
                return await self.llm.generate(state)
            except Exception:
                pass
        # 兜底：基于工具观察拼装（无 LLM 时仍可闭环，评估/离线可用）
        if state.observations:
            last = state.observations[-1]
            if isinstance(last, dict) and last.get("answer"):
                return str(last["answer"])
            return f"已检索到 {len(state.observations)} 条相关信息：{str(last)[:800]}"
        docs = state.docs or []
        if docs:
            return f"找到 {len(docs)} 条相关知识，首条：{str(docs[0])[:500]}"
        return "知识库暂无相关内容，已拒答（可补充文档后重试）。"
