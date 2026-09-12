"""Celery App（可选依赖：未安装/无 Redis 时降级为内存直跑，保证可启动）。"""
from app.core.config import settings

celery_app = None
try:
    from celery import Celery

    celery_app = Celery("agent-backend", broker=getattr(settings, "REDIS_URL", "redis://localhost:6379/0"))
    celery_app.conf.update(task_track_started=True, task_acks_late=True,
                           broker_connection_retry_on_startup=True)
except Exception:  # pragma: no cover
    celery_app = None
