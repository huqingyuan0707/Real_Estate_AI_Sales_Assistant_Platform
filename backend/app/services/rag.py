"""RAG 检索链（在线问答侧，对齐企业级 RAG 文档第三 / 四节）

链路：Query → 双路召回（向量语义 + 关键词）→ RRF 融合 → bge-reranker 重排
      → 治理双阶段过滤（检索前硬过滤 + 检索后部门/生效期精过滤）→ 多样性裁剪 → 阈值拒答

存储解耦（文档第三节「向量库可替换」）：
- 向量读写走 services/vector_store：chroma（默认）/ milvus（可选，不可用自动回退）
- 关键词检索走 services/keyword_store：内置 BM25（默认）/ elasticsearch（可选，同样回退）
- 缓存键含知识库版本号，索引变更自动失效；父块文本见 services/parents

模型惰性加载（首次调用经 HF_ENDPOINT 镜像下载并缓存）。
"""
import copy
import os
import threading
import time

from app.config import settings
from app.services import cache, governance, keyword_store, parents, query_expand, vector_store

os.environ.setdefault("HF_ENDPOINT", settings.HF_ENDPOINT)  # 须在 ST import 前设置

import numpy as np  # noqa: E402

_embed_model = None
_rerank_model = None
_kb_rev = 0                 # 知识库版本号：写入/删除/回填/重建时递增 → 缓存与 BM25 索引失效
_meta_checked = False
_meta_lock = threading.Lock()


# ---------------- 惰性单例 ----------------

def _get_embed():
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer(settings.RAG_EMBED_MODEL)
    return _embed_model


def _get_reranker():
    global _rerank_model
    if _rerank_model is None:
        from sentence_transformers import CrossEncoder
        _rerank_model = CrossEncoder(settings.RAG_RERANK_MODEL, max_length=512)
    return _rerank_model


def backend():
    """向量存储后端（Chroma / Milvus，配置不可用自动回退）"""
    return vector_store.get_backend(settings.RAG_EMBED_DIM)


def keyword_backend():
    """关键词检索后端（内置 BM25 / Elasticsearch）"""
    return keyword_store.get_backend(lambda: backend().get())


def _bump_rev() -> None:
    global _kb_rev
    _kb_rev += 1


def kb_count() -> int:
    return backend().count()


def kb_revision() -> int:
    """知识库版本号（写入/删除/回填/重建时递增），供缓存键与前端展示变更状态"""
    return _kb_rev


# ---------------- 存量向量治理字段回填 ----------------

def ensure_meta_defaults() -> int:
    """给治理字段上线前入库的向量补齐默认值（内部/已发布/全公司/长期有效）"""
    global _meta_checked, _kb_rev
    if _meta_checked:
        return 0
    with _meta_lock:
        if _meta_checked:
            return 0
        _meta_checked = True
        store = backend()
        if store.count() == 0:
            return 0
        data = store.get()
        ids, metas = [], []
        for i, m in enumerate(data.get("metadatas") or []):
            m = m or {}
            if "tenant_id" in m and "security_level" in m and "review_status" in m:
                continue
            fixed = {**governance.DEFAULT_META, **m}
            if not fixed.get("title"):
                fixed["title"] = fixed.get("source", "")
            ids.append(data["ids"][i])
            metas.append(fixed)
        if ids:
            store.update(ids, metas)
            _kb_rev += 1
        return len(ids)


# ---------------- 写入 / 删除 / 元数据维护 ----------------

def add_chunks(chunks: list[dict]) -> int:
    """chunks: [{text, metadata}] → 向量化写入向量库，并同步关键词索引"""
    if not chunks:
        return 0
    texts = [c["text"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]
    embeddings = _get_embed().encode(texts, normalize_embeddings=True).tolist()
    base_id = f"{metadatas[0]['source']}-{int(time.time() * 1000)}"
    ids = [f"{base_id}-{i}" for i in range(len(texts))]

    store = backend()
    store.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
    kw = keyword_backend()
    if hasattr(kw, "sync_add"):
        try:
            kw.sync_add(ids, texts, metadatas)
        except Exception:
            pass          # 关键词索引同步失败不影响向量主链路（检索时按 rev 重建）
    _bump_rev()
    return len(texts)


def delete_by_source(source: str) -> int:
    """按源文件删除：向量 + 关键词索引 + 父块文本（升版本或删除文档时调用）"""
    store = backend()
    before = store.count()
    store.delete(where={"source": source})
    deleted = before - store.count()
    kw = keyword_backend()
    if hasattr(kw, "sync_delete"):
        try:
            kw.sync_delete({"source": source})
        except Exception:
            pass
    parents.drop_source(source)
    if deleted:
        _bump_rev()
    return deleted


def update_source_meta(source: str, patch: dict) -> int:
    """批量更新某源文件全部分块的元数据（审核状态 / 生效期 / 密级变更后调用），
    使检索过滤条件立即生效，无需重新入库。"""
    store = backend()
    data = store.get(where={"source": source})
    ids = data.get("ids") or []
    if not ids:
        return 0
    metas = [{**(m or {}), **patch} for m in data["metadatas"]]
    store.update(ids, metas)
    _bump_rev()
    return len(ids)


def list_sources() -> list[dict]:
    """索引中的源文件清单（文件名 → 块数/分类/治理标签）"""
    store = backend()
    if store.count() == 0:
        return []
    data = store.get()
    stats: dict[str, dict] = {}
    for m in data.get("metadatas") or []:
        m = m or {}
        s = stats.setdefault(m.get("source", ""), {
            "name": m.get("source", ""),
            "category": m.get("category", ""),
            "chunks": 0,
            "security_level": m.get("security_level", governance.DEFAULT_LEVEL),
            "review_status": m.get("review_status", governance.DEFAULT_REVIEW),
            "dept_id": m.get("dept_id", ""),
            "owner": m.get("owner", ""),
            "version": m.get("doc_version", 1),
        })
        s["chunks"] += 1
    return sorted(stats.values(), key=lambda x: -x["chunks"])


def governance_stats() -> dict:
    """治理维度分布统计（运营看板：密级 / 部门 / 审核态）"""
    store = backend()
    if store.count() == 0:
        return {"by_level": {}, "by_dept": {}, "by_review": {}, "total": 0}
    data = store.get()
    by_level: dict[str, int] = {}
    by_dept: dict[str, int] = {}
    by_review: dict[str, int] = {}
    for m in data.get("metadatas") or []:
        m = m or {}
        lv = m.get("security_level", governance.DEFAULT_LEVEL)
        dp = m.get("dept_id") or "全公司"
        rv = m.get("review_status", governance.DEFAULT_REVIEW)
        by_level[lv] = by_level.get(lv, 0) + 1
        by_dept[dp] = by_dept.get(dp, 0) + 1
        by_review[rv] = by_review.get(rv, 0) + 1
    return {"by_level": by_level, "by_dept": by_dept, "by_review": by_review, "total": store.count()}


# ---------------- 召回第一路：向量语义 ----------------

def _vector_search(query: str, top_k: int, where: dict | None) -> list[dict]:
    store = backend()
    total = store.count()
    if total == 0:
        return []
    emb = _get_embed().encode([query], normalize_embeddings=True).tolist()[0]
    res = store.query(emb, min(top_k, total), where)
    dists = res.get("distances") or []
    return [{
        "id": res["ids"][i],
        "text": res["documents"][i],
        "metadata": res["metadatas"][i] or {},
        "distance": dists[i] if i < len(dists) else 1.0,
    } for i in range(len(res["ids"]))]


# ---------------- 召回第二路：关键词 ----------------

def _keyword_search(query: str, top_k: int, where: dict | None) -> list[dict]:
    hits = keyword_backend().search(query, top_k, where, _kb_rev)
    return [{"id": h["id"], "text": h["text"], "metadata": h["metadata"] or {},
             "bm25": h.get("score")} for h in hits]


# ---------------- 融合与重排 ----------------

def _rrf_fuse(runs: list[list[dict]], k: int = 60) -> list[dict]:
    """RRF 融合多路召回：score = Σ 1/(k + rank)，按向量 id 去重合并"""
    merged: dict[str, dict] = {}
    for run in runs:
        for rank, item in enumerate(run):
            key = item.get("id") or f"{item['metadata'].get('source')}-{item['metadata'].get('chunk_index')}"
            contrib = 1.0 / (k + rank + 1)
            cur = merged.get(key)
            if cur is None:
                merged[key] = {**item, "rrf": contrib, "routes": 1}
            else:
                cur["rrf"] = round(cur["rrf"] + contrib, 6)
                cur["routes"] += 1
    # 双路都命中的片段优先（routes 降序），再按 RRF 分数
    return sorted(merged.values(), key=lambda x: (-x["routes"], -x["rrf"]))


def _rerank(query: str, candidates: list[dict]) -> list[dict]:
    if not candidates:
        return []
    model = _get_reranker()
    pairs = [[query, c["text"]] for c in candidates]
    logits = model.predict(pairs)
    scores = 1 / (1 + np.exp(-logits))  # sigmoid → 相关度 0~1
    for c, s in zip(candidates, scores):
        c["score"] = float(s)
    return sorted(candidates, key=lambda x: -x["score"])


def _merge_filters(where: dict, filters: dict | None) -> dict:
    """结构化过滤（元数据过滤）：分类 / 密级 / 部门等条件叠加到治理条件之上"""
    if not filters:
        return where
    conds = list(where.get("$and", []))
    for key in ("category", "security_level", "dept_id"):
        value = filters.get(key)
        if value:
            vals = [value] if isinstance(value, str) else list(value)
            conds.append({key: {"$in": vals}})
    return {"$and": conds}


def _diversify(hits: list[dict], max_per_section: int) -> list[dict]:
    """结果多样性：同一章节最多保留 N 条，避免上下文被同段落重复占满"""
    if max_per_section <= 0:
        return hits
    out: list[dict] = []
    seen: dict[str, int] = {}
    for h in hits:
        m = h.get("metadata") or {}
        key = f"{m.get('source')}#{m.get('section')}"
        if seen.get(key, 0) >= max_per_section:
            continue
        seen[key] = seen.get(key, 0) + 1
        out.append(h)
    return out


# ---------------- 完整检索链 ----------------

def retrieve(query: str, ctx: dict | None = None, filters: dict | None = None) -> tuple[list[dict], bool, dict]:
    """完整检索链 + 治理过滤 + 结构化过滤。

    filters: {"category" / "security_level" / "dept_id": str|list} 限定检索范围（元数据过滤）
    返回 (片段列表, 是否因相关度不足触发拒答, 链路 trace)
    """
    t0 = time.time()
    trace: dict = {"query": query, "recall": {}, "blocked": 0, "blocked_reasons": [],
                   "final": 0, "top_score": 0.0, "elapsed_ms": {}}
    if kb_count() == 0:
        return [], True, {**trace, "reason": "empty_kb"}

    ensure_meta_defaults()
    ctx = ctx or governance.access_context()

    ck = cache.key_of("retrieve", query, ctx.get("tenant_id"), list(ctx.get("levels") or []),
                      ctx.get("dept"), _kb_rev, filters or {})
    cached = cache.retrieval_cache.get(ck)
    if cached is not None:
        hit_trace = {**cached["trace"], "from_cache": True}
        hit_trace["elapsed_ms"] = {**hit_trace.get("elapsed_ms", {}),
                                   "total": round((time.time() - t0) * 1000, 1)}
        return copy.deepcopy(cached["hits"]), cached["rejected"], hit_trace

    where = _merge_filters(governance.build_where(ctx), filters)
    recall_k = max(settings.RAG_TOP_K * settings.RAG_RECALL_MULTIPLIER, 20)

    t = time.time()
    v_hits = _vector_search(query, recall_k, where)
    trace["elapsed_ms"]["vector"] = round((time.time() - t) * 1000, 1)

    t = time.time()
    # 关键词路使用同义词扩展后的查询；向量路与重排保持原始问句，避免语义漂移
    bm25_query, expansions = query_expand.expand(query)
    b_hits = _keyword_search(bm25_query, recall_k, where)
    trace["elapsed_ms"]["keyword"] = round((time.time() - t) * 1000, 1)

    trace["query_expansion"] = expansions
    trace["recall"] = {"vector": len(v_hits), "keyword": len(b_hits)}
    fused = _rrf_fuse([v_hits, b_hits], k=settings.RAG_RRF_K)[:recall_k]

    t = time.time()
    ranked = _rerank(query, fused)
    trace["elapsed_ms"]["rerank"] = round((time.time() - t) * 1000, 1)

    # 治理阶段二：部门 / 生效期精过滤（越权片段一律丢弃并记录原因）
    visible, blocked = governance.filter_hits(ranked, ctx)
    trace["blocked"] = len(blocked)
    trace["blocked_reasons"] = sorted({b.get("blocked_reason", "") for b in blocked})

    passed = [h for h in visible if h["score"] >= settings.RAG_MIN_SCORE]
    hits = _diversify(passed, settings.RAG_MAX_PER_SECTION)[: settings.RAG_FINAL_K]
    for h in hits:
        h.pop("distance", None)
    trace["final"] = len(hits)
    trace["top_score"] = round(hits[0]["score"], 3) if hits else 0.0
    trace["elapsed_ms"]["total"] = round((time.time() - t0) * 1000, 1)
    rejected = len(hits) == 0
    cache.retrieval_cache.set(ck, {"hits": copy.deepcopy(hits), "rejected": rejected, "trace": trace},
                              settings.RAG_CACHE_TTL)
    return hits, rejected, trace


def storage_status() -> dict:
    """存储后端状态（诊断与合规自查）：向量后端 / 关键词后端 / 是否发生回退"""
    return {
        "vector": vector_store.status(),
        "keyword": keyword_store.status(),
        "kb_chunks": kb_count(),
        "kb_revision": _kb_rev,
        "embed_model": settings.RAG_EMBED_MODEL,
        "embed_dim": settings.RAG_EMBED_DIM,
    }
