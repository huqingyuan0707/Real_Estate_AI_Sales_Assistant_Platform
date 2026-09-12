"""工程化配置兼容层（文档：app/core/config.py）。

本仓真实配置在 app/config.py（已承载 LLM/RAG 等全量配置）。
此模块做薄适配：复用同一 settings 单例，并补齐文档中的通用字段，
使外部文档代码 `from app.core.config import settings` 可直接运行。
"""
from app.config import settings  # noqa: F401  (单例复用，保证全局一致)

# 补齐文档字段（不存在则给安全默认值，避免 Settings 校验失败影响启动）
_DEFAULTS: dict = {
    "APP_NAME": getattr(settings, "APP_NAME", "agent-backend"),
    "ENV": "dev",
    "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/agent",
    "REDIS_URL": "redis://localhost:6379/0",
    "VECTOR_DB_URL": "postgresql://localhost:5432/agent",
}
for _k, _v in _DEFAULTS.items():
    if not hasattr(settings, _k):
        setattr(settings, _k, _v)
if not hasattr(settings, "JWT_SECRET"):
    setattr(settings, "JWT_SECRET", getattr(settings, "SECRET_KEY", "reai-demo-secret-change-in-prod"))
