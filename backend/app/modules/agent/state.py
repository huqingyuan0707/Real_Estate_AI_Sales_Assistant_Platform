"""Agent 状态机（IDLE→PLANNING→ACTING→OBSERVING→REFLECTING→DONE，
分支 WAITING_APPROVAL / FAILED）。状态可持久化/恢复/重试，每步携带 trace_id。"""
from dataclasses import dataclass, field
from typing import Any


class AgentPhase:
    IDLE = "IDLE"
    PLANNING = "PLANNING"
    ACTING = "ACTING"
    OBSERVING = "OBSERVING"
    REFLECTING = "REFLECTING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    DONE = "DONE"
    FAILED = "FAILED"


@dataclass
class AgentAction:
    type: str  # tool | answer | approval
    name: str = ""
    args: dict = field(default_factory=dict)
    idempotency_key: str | None = None


@dataclass
class AgentState:
    query: str
    user: dict | None = None
    context: Any = None
    docs: list = field(default_factory=list)
    phase: str = AgentPhase.IDLE
    observations: list = field(default_factory=list)
    answer: str = ""
    trace_id: str = ""
    done: bool = False
    approval: dict | None = None
    error: str | None = None

    def observe(self, result: Any) -> None:
        self.observations.append(result)
        self.phase = AgentPhase.OBSERVING

    def finish(self, answer: str) -> None:
        self.answer = answer
        self.phase = AgentPhase.DONE
        self.done = True

    def wait_approval(self, action: AgentAction) -> None:
        self.phase = AgentPhase.WAITING_APPROVAL
        self.approval = {"name": action.name, "args": action.args}
        self.done = True  # 暂停执行，等待外部 resume

    def fail(self, message: str) -> None:
        self.phase = AgentPhase.FAILED
        self.error = message
        self.done = True

    def to_result(self) -> dict:
        return {"answer": self.answer, "trace_id": self.trace_id, "phase": self.phase}

    # 检查点：状态持久化（任务中心/断点续聊用）
    def checkpoint(self) -> dict:
        return {
            "query": self.query, "phase": self.phase, "observations": self.observations,
            "answer": self.answer, "trace_id": self.trace_id, "done": self.done,
            "approval": self.approval, "error": self.error,
        }

    @classmethod
    def restore(cls, data: dict) -> "AgentState":
        return cls(
            query=data.get("query", ""), phase=data.get("phase", AgentPhase.IDLE),
            observations=data.get("observations", []), answer=data.get("answer", ""),
            trace_id=data.get("trace_id", ""), done=data.get("done", False),
            approval=data.get("approval"), error=data.get("error"),
        )
