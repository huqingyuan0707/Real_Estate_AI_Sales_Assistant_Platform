"""SQLAlchemy Base（可选依赖：未安装时提供占位，保证无 DB 开发机可启动）。"""
try:
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):
        pass
except Exception:  # pragma: no cover

    class Base:  # type: ignore
        metadata = None
