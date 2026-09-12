"""长任务表（tasks：状态查询/检查点/恢复/重试），对齐文档第十节。"""
try:
    from sqlalchemy import JSON, DateTime, String, Text
    from sqlalchemy.orm import Mapped, mapped_column

    from app.db.base import Base

    class Task(Base):
        __tablename__ = "tasks"
        id: Mapped[str] = mapped_column(String(64), primary_key=True)
        tenant_id: Mapped[str] = mapped_column(String(64), default="")
        user_id: Mapped[str] = mapped_column(String(64), default="")
        agent_id: Mapped[str] = mapped_column(String(64), default="default")
        status: Mapped[str] = mapped_column(String(32), default="queued")
        input: Mapped[dict] = mapped_column(JSON, default=dict)
        output: Mapped[dict] = mapped_column(JSON, default=dict)
        error: Mapped[str] = mapped_column(Text, default="")
        checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)
except Exception:  # pragma: no cover — 无 SQLAlchemy 时占位

    class Task:  # type: ignore
        __tablename__ = "tasks"
