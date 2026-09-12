"""向量存储适配层（对齐企业级 RAG 文档第三节：向量库可替换、索引可回滚）

统一契约（rag.py 只依赖本层，不直接触达具体库）：
    count() / add(ids, embeddings, documents, metadatas) / query(embedding, n, where)
    get(where, limit) / update(ids, metadatas) / delete(where) / reset()

后端由配置 VECTOR_BACKEND 选择：
- chroma（默认）：本地持久化、零运维，适合单机与演示
- milvus：pymilvus 连接 MILVUS_URI，适合大规模生产；
  客户端未安装 / 连接失败 → **自动回退 chroma 并记录状态**（status() 可见），不阻塞业务

切换语义：两套后端都实现了同一 where 过滤语义（$and / 等值 / $in / $gte / $lte），
业务代码无需改动。
"""
import threading
import time

from app.config import settings

_LOCK = threading.Lock()
_CACHE: dict = {}
_STATUS = {"backend": None, "fallback_reason": "", "since": ""}


# ---------------- 条件转换（统一 where → 各家语法） ----------------

def _literal(v) -> str:
    """Milvus 表达式字面量：字符串加引号并转义，数字/布尔原样"""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return '"' + str(v).replace('"', '\\"') + '"'


def to_milvus_expr(where: dict | None) -> str:
    """把统一 where（Chroma 风格）翻译为 Milvus 布尔表达式"""
    if not where:
        return ""
    conds = where.get("$and") or [where]
    parts: list[str] = []
    for cond in conds:
        for key, expect in cond.items():
            if isinstance(expect, dict):
                if "$in" in expect:
                    vals = ", ".join(_literal(x) for x in expect["$in"])
                    parts.append(f"{key} in [{vals}]")
                elif "$lte" in expect:
                    parts.append(f"{key} <= {_literal(expect['$lte'])}")
                elif "$gte" in expect:
                    parts.append(f"{key} >= {_literal(expect['$gte'])}")
                elif "$ne" in expect:
                    parts.append(f"{key} != {_literal(expect['$ne'])}")
                continue
            parts.append(f"{key} == {_literal(expect)}")
    return " and ".join(parts)


# ---------------- Chroma 后端（默认） ----------------

class ChromaBackend:
    name = "chroma"

    def __init__(self, path: str, collection: str):
        import chromadb
        self._client = chromadb.PersistentClient(path=path)
        self._collection_name = collection
        self._col = self._client.get_or_create_collection(
            collection, metadata={"hnsw:space": "cosine"},
        )

    def count(self) -> int:
        return self._col.count()

    def add(self, ids, embeddings, documents, metadatas) -> None:
        self._col.add(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)

    def query(self, embedding: list[float], n_results: int, where: dict | None = None) -> dict:
        kw = {"where": where} if where else {}
        res = self._col.query(query_embeddings=[embedding], n_results=n_results, **kw)
        return {
            "ids": res["ids"][0], "documents": res["documents"][0],
            "metadatas": res["metadatas"][0],
            "distances": (res.get("distances") or [[]])[0],
        }

    def get(self, where: dict | None = None, limit: int | None = None,
            with_embeddings: bool = False) -> dict:
        kw: dict = {}
        if where:
            kw["where"] = where
        if limit:
            kw["limit"] = limit
        include = ["documents", "metadatas"] + (["embeddings"] if with_embeddings else [])
        res = self._col.get(include=include, **kw)
        out = {"ids": res["ids"], "documents": res["documents"], "metadatas": res["metadatas"]}
        if with_embeddings:
            out["embeddings"] = res.get("embeddings")
        return out

    def update(self, ids, metadatas) -> None:
        self._col.update(ids=ids, metadatas=metadatas)

    def delete(self, where: dict) -> None:
        self._col.delete(where=where)

    def reset(self) -> None:
        """删除并重建集合（索引重建 / 回滚用）"""
        try:
            self._client.delete_collection(self._collection_name)
        except Exception:
            pass
        self._col = self._client.get_or_create_collection(
            self._collection_name, metadata={"hnsw:space": "cosine"},
        )


# ---------------- Milvus 后端（可选） ----------------

class MilvusBackend:
    """Milvus 适配器：metadata 扁平写入动态字段，便于 where 过滤

    依赖 pymilvus（未安装时构造抛 ImportError → 工厂自动回退 chroma）。
    """

    name = "milvus"

    def __init__(self, uri: str, collection: str, dim: int):
        from pymilvus import (Collection, CollectionSchema, DataType, FieldSchema,
                              connections, utility)
        connections.connect(alias="default", uri=uri)
        self._collection_name = collection
        self._dim = dim
        if not utility.has_collection(collection):
            schema = CollectionSchema([
                FieldSchema("id", DataType.VARCHAR, is_primary=True, max_length=512),
                FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=dim),
                FieldSchema("text", DataType.VARCHAR, max_length=65535),
            ], description="reai_kb", enable_dynamic_field=True)
            col = Collection(collection, schema)
            col.create_index("embedding", {"index_type": "HNSW", "metric_type": "COSINE",
                                           "params": {"M": 16, "efConstruction": 200}})
        self._col = Collection(collection)
        self._col.load()

    @staticmethod
    def _row_meta(meta: dict) -> dict:
        """动态字段只接受标量；非标量转字符串"""
        return {k: (v if isinstance(v, (str, int, float, bool)) else str(v))
                for k, v in (meta or {}).items()}

    def count(self) -> int:
        return self._col.num_entities

    def add(self, ids, embeddings, documents, metadatas) -> None:
        rows = []
        for i, _id in enumerate(ids):
            rows.append({"id": _id, "embedding": list(embeddings[i]), "text": documents[i],
                         **self._row_meta(metadatas[i])})
        self._col.insert(rows)
        self._col.flush()

    def query(self, embedding: list[float], n_results: int, where: dict | None = None) -> dict:
        expr = to_milvus_expr(where)
        res = self._col.search(
            data=[list(embedding)], anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"ef": 128}},
            limit=max(1, n_results), expr=expr or None, output_fields=["*"],
        )
        ids, docs, metas, dists = [], [], [], []
        for hit in res[0]:
            ids.append(hit.id)
            entity = hit.entity
            docs.append(entity.get("text") or "")
            meta = {}
            for k in (entity.fields or []):
                if k in ("id", "embedding", "text"):
                    continue
                meta[k] = entity.get(k)
            metas.append(meta)
            dists.append(1.0 - float(hit.score))     # COSINE 相似度 → 距离
        return {"ids": ids, "documents": docs, "metadatas": metas, "distances": dists}

    def get(self, where: dict | None = None, limit: int | None = None,
            with_embeddings: bool = False) -> dict:
        expr = to_milvus_expr(where)
        rows = self._col.query(expr=expr or None, output_fields=["*"],
                              limit=limit or 16384)
        ids = [r["id"] for r in rows]
        docs = [r.get("text", "") for r in rows]
        skip = {"id", "embedding", "text"}
        metas = [{k: v for k, v in r.items() if k not in skip} for r in rows]
        out = {"ids": ids, "documents": docs, "metadatas": metas}
        if with_embeddings:
            out["embeddings"] = [r.get("embedding") for r in rows]
        return out

    def update(self, ids, metadatas) -> None:
        """Milvus 不支持原地改元数据：按 upsert 语义重写动态字段（保留原文与向量）"""
        existing = self.get()
        by_id = {i: (d, m) for i, d, m in zip(existing["ids"], existing["documents"], existing["metadatas"])}
        emb = self._col.query(expr=f"id in [{', '.join(_literal(i) for i in ids)}]",
                              output_fields=["id", "embedding"]) if ids else []
        emb_map = {r["id"]: r["embedding"] for r in emb}
        rows = []
        for i, meta in zip(ids, metadatas):
            doc, old = by_id.get(i, ("", {}))
            rows.append({"id": i, "embedding": emb_map.get(i), "text": doc,
                         **self._row_meta({**old, **meta})})
        self._col.upsert(rows)
        self._col.flush()

    def delete(self, where: dict) -> None:
        expr = to_milvus_expr(where)
        if expr:
            self._col.delete(expr)
            self._col.flush()

    def reset(self) -> None:
        from pymilvus import utility
        if utility.has_collection(self._collection_name):
            utility.drop_collection(self._collection_name)
        self.__init__(settings.MILVUS_URI, self._collection_name, self._dim)


# ---------------- 工厂 ----------------

def get_backend(dim: int = 512):
    """按配置返回向量后端单例；配置为 milvus 但不可用时回退 chroma（记录原因）"""
    key = f"{settings.VECTOR_BACKEND}:{dim}"
    with _LOCK:
        backend = _CACHE.get(key)
        if backend is not None:
            return backend

        if settings.VECTOR_BACKEND.lower() == "milvus":
            try:
                backend = MilvusBackend(settings.MILVUS_URI, settings.MILVUS_COLLECTION, dim)
                _STATUS.update(backend="milvus", fallback_reason="", since=time.strftime("%Y-%m-%d %H:%M:%S"))
                _CACHE[key] = backend
                return backend
            except Exception as e:  # 未安装 pymilvus / 连不上 → 回退
                _STATUS.update(backend="chroma", since=time.strftime("%Y-%m-%d %H:%M:%S"),
                               fallback_reason=f"milvus 不可用（{type(e).__name__}: {str(e)[:120]}），已回退 chroma")

        backend = ChromaBackend(settings.RAG_CHROMA_DIR, "reai_kb")
        if not _STATUS["backend"]:
            _STATUS.update(backend="chroma", since=time.strftime("%Y-%m-%d %H:%M:%S"))
        _CACHE[key] = backend
        return backend


def status() -> dict:
    """存储后端状态（供诊断接口与合规自查）"""
    return {
        "configured": settings.VECTOR_BACKEND,
        "active": _STATUS.get("backend"),
        "fallback_reason": _STATUS.get("fallback_reason", ""),
        "since": _STATUS.get("since", ""),
        "milvus_uri": settings.MILVUS_URI if settings.VECTOR_BACKEND.lower() == "milvus" else "",
    }
