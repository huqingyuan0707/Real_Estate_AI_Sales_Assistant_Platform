"""异步 Session 工厂（DATABASE_URL 未配置/驱动缺失时返回 None，由调用方降级）。"""
from app.core.config import settings

_async_session = None


def get_engine():
    try:
        from sqlalchemy.ext.asyncio import create_async_engine

        url = getattr(settings, "DATABASE_URL", "")
        if not url:
            return None
        return create_async_engine(url, pool_pre_ping=True)
    except Exception:
        return None


async def get_session():
    """FastAPI Depends：yield AsyncSession | None。"""
    engine = get_engine()
    if engine is None:
        yield None
        return
    try:
        from sqlalchemy.ext.asyncio import async_sessionmaker

        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            yield session
    finally:
        await engine.dispose()
