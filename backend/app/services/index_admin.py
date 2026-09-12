"""索引版本管理与增量同步（对齐企业级 RAG 文档第三节"嵌入与索引"）

- 版本记录：入库/删除/重建时记录 (revision, embed_model, 分块数, 操作人, 时间) 到 data/index_versions.json
- 换模型重建：用新嵌入模型对库内原文整库重新向量化（原文保存在向量库 payload 中，可重编码）
  重建前自动快照 ids/documents/metadatas/**embeddings**（含模型名与维度），可一键原样回滚
- 增量同步：按文件 SHA256 指纹对比，只处理新增/变更文件（见 endpoints/documents.py 的 /sync）

后端无关：向量读写统一走 services/vector_store，因此 chroma ↔ milvus 切换后上述能力同样可用。
"""
import hashlib
import json
import os
import time
from pathlib import Path

from app.config import settings
from app.services import rag, vector_store

_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_VERSIONS_PATH = _DATA_DIR / "index_versions.json"
_BACKUP_DIR = _DATA_DIR / "index_backups"


def file_fingerprint(path: str | Path) -> str:
    """文件内容指纹（SHA256，流式读取，避免大文件占内存）"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def _load_versions() -> dict:
    try:
        with open(_VERSIONS_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"current": None, "history": []}


def _save_versions(data: dict) -> None:
    _VERSIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = f"{_VERSIONS_PATH}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _VERSIONS_PATH)


def record(reason: str, *, username: str = "") -> dict:
    """记录一次索引版本快照"""
    entry = {
        "revision": rag.kb_revision(),
        "embed_model": settings.RAG_EMBED_MODEL,
        "embed_dim": settings.RAG_EMBED_DIM,
        "chunks": rag.kb_count(),
        "backend": vector_store.status().get("active"),
        "reason": reason,
        "by": username,
        "at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    data = _load_versions()
    data["current"] = entry
    history = data.get("history") or []
    history.insert(0, entry)
    data["history"] = history[:50]
    _save_versions(data)
    return entry


def versions() -> dict:
    return _load_versions()


def list_backups() -> list[dict]:
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for p in sorted(_BACKUP_DIR.glob("*.json"), reverse=True):
        out.append({"name": p.name, "size_mb": round(p.stat().st_size / 1024 / 1024, 2),
                    "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))})
    return out


def _probe_dim() -> int:
    """探测当前嵌入模型输出维度（换模型后用于重建向量库）"""
    try:
        vec = rag._get_embed().encode(["dimension probe"]).tolist()[0]
        return int(len(vec))
    except Exception:
        return settings.RAG_EMBED_DIM


def _switch_model(model: str | None) -> None:
    """切换嵌入模型并清空后端缓存（维度或索引结构变化时需重建连接）"""
    if model and model != settings.RAG_EMBED_MODEL:
        settings.RAG_EMBED_MODEL = model
    rag._embed_model = None
    settings.RAG_EMBED_DIM = _probe_dim()
    vector_store._CACHE.clear()       # 按新维度重新建立向量后端
    reread = vector_store.get_backend(settings.RAG_EMBED_DIM)
    _ = reread                        # 触发构建，尽早暴露不可用（便于回退）


def rebuild(new_embed_model: str | None = None, *, username: str = "") -> dict:
    """换嵌入模型整库重建：先快照（含向量），再用新模型重编码"""
    store = rag.backend()
    data = store.get(with_embeddings=True)
    ids = data.get("ids") or []
    if not ids:
        return {"rebuilt": 0, "message": "知识库为空，无需重建"}

    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    snap_name = f"index_backup_rev{rag.kb_revision()}_{int(time.time())}.json"
    with open(_BACKUP_DIR / snap_name, "w", encoding="utf-8") as f:
        json.dump({
            "ids": ids, "documents": data["documents"], "metadatas": data["metadatas"],
            "embeddings": data.get("embeddings"), "model": settings.RAG_EMBED_MODEL,
            "dim": settings.RAG_EMBED_DIM, "chunks": len(ids),
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, f, ensure_ascii=False)

    old_model = settings.RAG_EMBED_MODEL
    _switch_model(new_embed_model)

    new_store = rag.backend()
    new_store.reset()
    rag._bump_rev()
    n = rag.add_chunks([{"text": d, "metadata": m}
                        for d, m in zip(data["documents"], data["metadatas"])])
    entry = record("rebuild", username=username)
    return {"rebuilt": n, "embed_model": settings.RAG_EMBED_MODEL, "previous_model": old_model,
            "embed_dim": settings.RAG_EMBED_DIM, "backend": vector_store.status().get("active"),
            "backup": snap_name, "revision": entry["revision"]}


def rollback(backup_name: str, *, username: str = "") -> dict:
    """回滚到指定快照：原样写回 ids / documents / metadatas / embeddings"""
    path = _BACKUP_DIR / backup_name
    if not path.exists():
        raise FileNotFoundError(f"快照不存在：{backup_name}")
    with open(path, encoding="utf-8") as f:
        snap = json.load(f)
    if not snap.get("embeddings"):
        raise ValueError("快照缺少向量数据，无法回滚")

    if snap.get("model"):
        settings.RAG_EMBED_MODEL = snap["model"]
    if snap.get("dim"):
        settings.RAG_EMBED_DIM = int(snap["dim"])
    rag._embed_model = None
    vector_store._CACHE.clear()
    vector_store.get_backend(settings.RAG_EMBED_DIM)

    store = rag.backend()
    store.reset()
    store.add(ids=snap["ids"], embeddings=snap["embeddings"], documents=snap["documents"],
              metadatas=snap["metadatas"])
    rag._bump_rev()

    kw = rag.keyword_backend()
    if hasattr(kw, "sync_add"):
        try:
            kw.sync_add(snap["ids"], snap["documents"], snap["metadatas"])
        except Exception:
            pass

    entry = record(f"rollback:{backup_name}", username=username)
    return {"restored": len(snap["ids"]), "backup": backup_name,
            "embed_model": settings.RAG_EMBED_MODEL, "revision": entry["revision"]}


def sync_keyword_index() -> dict:
    """把向量库全量同步到外部关键词后端（ES 场景下首次接入或重建后调用）"""
    kw = rag.keyword_backend()
    if not hasattr(kw, "sync_add"):
        return {"synced": 0, "message": f"当前关键词后端为 {kw.name}，无需同步"}
    data = rag.backend().get()
    ids = data.get("ids") or []
    if ids:
        kw.sync_add(ids, data["documents"], data["metadatas"])
        rag._bump_rev()
    return {"synced": len(ids), "backend": kw.name}
