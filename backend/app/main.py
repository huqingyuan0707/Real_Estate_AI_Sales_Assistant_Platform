"""应用入口（工厂模式）。启动：uvicorn app.main:app --reload --port 8000"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.config import settings
from app.core.events import on_shutdown, on_startup
from app.core.exceptions import register_exception_handlers
from app.core.middleware import TraceMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    await on_startup()
    yield
    await on_shutdown()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="房地产AI销售助手平台 API（页面设计阶段：全部接口返回 Mock 数据）",
        lifespan=lifespan,
    )
    app.add_middleware(TraceMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    register_exception_handlers(app)

    @app.get("/api/health", tags=["系统"])
    def health():
        return {"status": "ok", "version": settings.APP_VERSION}

    @app.get("/health", tags=["系统"])
    def health_root():
        return {"status": "ok", "version": settings.APP_VERSION}

    @app.get("/ready", tags=["系统"])
    def ready():
        return {"status": "ready", "version": settings.APP_VERSION}

    return app


app = create_app()
