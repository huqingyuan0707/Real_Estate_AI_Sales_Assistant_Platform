"""系统设置接口：查看并管理模型、检索、分块等参数（运行时热更新）

知识库管理负责生产数据，智能问答负责消费数据，系统设置负责配置调优。
参数持久化写入 backend/.runtime_settings.json（重启保留）。
"""
import json
import os

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings
from app.core.responses import ok

router = APIRouter()

# 可热更新参数白名单（其余参数只读展示）
_HOT_FIELDS = {
    "LLM_MODEL": str,
    "RAG_TOP_K": int,
    "RAG_FINAL_K": int,
    "RAG_MIN_SCORE": float,
    "RAG_CHUNK_SIZE": int,
    "RAG_CHUNK_OVERLAP": int,
    "RAG_EMBED_MODEL": str,
    "RAG_RERANK_MODEL": str,
    "RENDER_SIM_SECONDS": float,
}
_PERSIST_PATH = os.path.join(os.path.dirname(settings.RAG_UPLOAD_DIR), ".runtime_settings.json")


def _load_persisted() -> dict:
    try:
        with open(_PERSIST_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _apply_persisted() -> None:
    for k, v in _load_persisted().items():
        if k in _HOT_FIELDS:
            setattr(settings, k, _HOT_FIELDS[k](v))


_apply_persisted()  # 启动时恢复


class SettingsUpdateRequest(BaseModel):
    llm_model: str | None = None
    rag_top_k: int | None = None
    rag_final_k: int | None = None
    rag_min_score: float | None = None
    rag_chunk_size: int | None = None
    rag_chunk_overlap: int | None = None


_FIELD_MAP = {
    "llm_model": "LLM_MODEL",
    "rag_top_k": "RAG_TOP_K",
    "rag_final_k": "RAG_FINAL_K",
    "rag_min_score": "RAG_MIN_SCORE",
    "rag_chunk_size": "RAG_CHUNK_SIZE",
    "rag_chunk_overlap": "RAG_CHUNK_OVERLAP",
}


@router.get("")
def get_settings():
    """当前系统参数（分组返回，供设置页渲染）"""
    return ok({
        "model": {
            "llm_base_url": settings.LLM_BASE_URL,
            "llm_model": settings.LLM_MODEL,
            "embed_model": settings.RAG_EMBED_MODEL,
            "rerank_model": settings.RAG_RERANK_MODEL,
            "comfyui_base_url": settings.COMFYUI_BASE_URL,
        },
        "retrieval": {
            "top_k": settings.RAG_TOP_K,
            "final_k": settings.RAG_FINAL_K,
            "min_score": settings.RAG_MIN_SCORE,
        },
        "chunking": {
            "chunk_size": settings.RAG_CHUNK_SIZE,
            "chunk_overlap": settings.RAG_CHUNK_OVERLAP,
        },
    })


@router.put("")
def update_settings(body: SettingsUpdateRequest):
    """更新可热更参数：立即生效（检索/分块/模型名），并持久化到 .runtime_settings.json"""
    updates: dict[str, object] = {}
    for field, key in _FIELD_MAP.items():
        value = getattr(body, field)
        if value is not None:
            setattr(settings, key, _HOT_FIELDS[key](value))
            updates[key] = value

    if updates:
        persisted = _load_persisted()
        persisted.update(updates)
        with open(_PERSIST_PATH, "w", encoding="utf-8") as f:
            json.dump(persisted, f, ensure_ascii=False, indent=2)

    return ok({"updated": list(updates.keys())}, "参数已更新并立即生效")
