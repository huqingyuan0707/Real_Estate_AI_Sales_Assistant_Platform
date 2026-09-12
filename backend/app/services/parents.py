"""父块存储（小块检索、大块生成，对齐企业级 RAG 文档第二节"父子上块"）

子块（RAG_CHUNK_SIZE）入库参与向量与关键词召回，保证检索精度；
父块（子块 × N）只存文本，命中子块后取父块注入 Prompt，保证上下文完整、语义不被切断。

存储：backend/data/parent_chunks.json（原子写，进程内缓存）；
父块 id 形如「文件名#页码#父块序号」，便于按源文件前缀清理（升版本/删除文档时）。
"""
import json
import os
import threading
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "data" / "parent_chunks.json"
_LOCK = threading.Lock()
_CACHE: dict[str, str] | None = None


def _load() -> dict[str, str]:
    global _CACHE
    if _CACHE is None:
        try:
            with open(_PATH, encoding="utf-8") as f:
                _CACHE = json.load(f)
        except Exception:
            _CACHE = {}
    return _CACHE


def _flush(data: dict[str, str]) -> None:
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = f"{_PATH}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, _PATH)


def put_many(items: dict[str, str]) -> int:
    if not items:
        return 0
    with _LOCK:
        data = _load()
        data.update(items)
        _flush(data)
        return len(items)


def get(parent_id: str) -> str:
    return _load().get(parent_id, "") if parent_id else ""


def drop_source(source: str) -> int:
    """按源文件清理其父块（同名升版本或删除文档时调用）"""
    prefix = f"{source}#"
    with _LOCK:
        data = _load()
        keys = [k for k in data if k.startswith(prefix)]
        for k in keys:
            data.pop(k, None)
        if keys:
            _flush(data)
        return len(keys)


def count() -> int:
    return len(_load())
