"""关键词检索后端（对齐企业级 RAG 文档第三、四节：全文索引与混合召回的关键词路）

统一契约：search(query, top_k, where, rev) → [{id, text, metadata, score}]
- builtin（默认）：进程内 BM25 倒排索引，中文按字符 bigram 切分，零依赖零运维
- elasticsearch：ES / OpenSearch 客户端（支持 IK 分词与 DSL 过滤），
  未安装客户端或连不上时 **自动回退 builtin 并记录状态**

索引维护：向量写入/删除后由 rag 调用 sync_add / sync_delete 保持关键词索引一致。
"""
import math
import re
import threading

from app.config import settings

_STATUS = {"backend": None, "fallback_reason": ""}

_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    """轻量中英混合分词：英文/数字按词切；中文按字符 bigram（免第三方分词依赖）"""
    tokens: list[str] = []
    for seg in _TOKEN_RE.findall((text or "").lower()):
        if seg[0].isascii():
            tokens.append(seg)
        elif len(seg) == 1:
            tokens.append(seg)
        else:
            tokens.extend(seg[i:i + 2] for i in range(len(seg) - 1))
    return tokens


def meta_match(meta: dict, where: dict | None) -> bool:
    """在应用层复现统一 where 的等值/集合语义（与向量层同一套过滤条件）"""
    conds = (where or {}).get("$and") if isinstance(where, dict) else None
    if not conds:
        return True
    for cond in conds:
        for key, expect in cond.items():
            actual = meta.get(key)
            if isinstance(expect, dict) and "$in" in expect:
                if actual not in expect["$in"]:
                    return False
            elif isinstance(expect, dict) and "$lte" in expect:
                if actual is None or float(actual) > float(expect["$lte"]):
                    return False
            elif isinstance(expect, dict) and "$gte" in expect:
                if actual is None or float(actual) < float(expect["$gte"]):
                    return False
            elif actual != expect:
                return False
    return True


def to_es_filter(where: dict | None) -> list[dict]:
    """统一 where → Elasticsearch bool.filter 子句列表"""
    if not where:
        return []
    conds = where.get("$and") or [where]
    out: list[dict] = []
    for cond in conds:
        for key, expect in cond.items():
            if isinstance(expect, dict):
                if "$in" in expect:
                    out.append({"terms": {key: list(expect["$in"])}})
                elif "$lte" in expect:
                    out.append({"range": {key: {"lte": expect["$lte"]}}})
                elif "$gte" in expect:
                    out.append({"range": {key: {"gte": expect["$gte"]}}})
                continue
            out.append({"term": {key: expect}})
    return out


class BuiltinBM25:
    """内置 BM25（Okapi），索引随知识库版本号失效重建"""

    name = "builtin"

    def __init__(self, fetcher):
        self._fetch = fetcher            # () -> {"ids", "documents", "metadatas"}
        self._idx: dict | None = None
        self._rev = -1
        self._lock = threading.Lock()

    def _build(self, rev: int) -> dict:
        data = self._fetch()
        tf_list, lens, df = [], [], {}
        for doc in data["documents"]:
            tf: dict[str, int] = {}
            for t in tokenize(doc):
                tf[t] = tf.get(t, 0) + 1
            tf_list.append(tf)
            lens.append(sum(tf.values()) or 1)
            for t in tf:
                df[t] = df.get(t, 0) + 1
        n = len(data["ids"])
        return {"rev": rev, "ids": data["ids"], "docs": data["documents"], "metas": data["metadatas"],
                "tf": tf_list, "df": df, "len": lens, "n": n,
                "avgdl": (sum(lens) / n if n else 0.0)}

    def _index(self, rev: int) -> dict:
        if self._idx is not None and self._rev == rev:
            return self._idx
        with self._lock:
            if self._idx is None or self._rev != rev:
                self._idx = self._build(rev)
                self._rev = rev
        return self._idx

    def search(self, query: str, top_k: int, where: dict | None, rev: int) -> list[dict]:
        idx = self._index(rev)
        if not idx["ids"]:
            return []
        q_tokens = set(tokenize(query))
        if not q_tokens:
            return []
        n, avgdl = idx["n"], idx["avgdl"] or 1.0
        scored = []
        for i, _id in enumerate(idx["ids"]):
            meta = idx["metas"][i]
            if not meta_match(meta, where):
                continue
            tf, dl = idx["tf"][i], idx["len"][i]
            score = 0.0
            for t in q_tokens:
                f = tf.get(t, 0)
                if not f:
                    continue
                df = idx["df"].get(t, 0)
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                score += idf * (f * (1.5 + 1)) / (f + 1.5 * (1 - 0.75 + 0.75 * dl / avgdl))
            if score > 0:
                scored.append({"id": _id, "text": idx["docs"][i], "metadata": meta,
                               "score": round(score, 4)})
        scored.sort(key=lambda x: -x["score"])
        return scored[:top_k]


class ElasticsearchKeyword:
    """Elasticsearch / OpenSearch 关键词后端（bulk 写入 + multi_match 检索）"""

    name = "elasticsearch"

    def __init__(self, url: str, index: str):
        from elasticsearch import Elasticsearch
        self._es = Elasticsearch(url, request_timeout=3, verify_certs=False)
        if not self._es.ping():
            raise ConnectionError(f"Elasticsearch 不可达：{url}")
        self._index = index
        if not self._es.indices.exists(index=index):
            self._es.indices.create(index=index, mappings={
                "properties": {
                    "text": {"type": "text"},
                    "title": {"type": "text"},
                    "source": {"type": "keyword"},
                    "category": {"type": "keyword"},
                    "tenant_id": {"type": "keyword"},
                    "dept_id": {"type": "keyword"},
                    "security_level": {"type": "keyword"},
                    "review_status": {"type": "keyword"},
                    "page": {"type": "integer"},
                }
            })

    def sync_add(self, ids, documents, metadatas) -> None:
        ops = []
        for i, _id in enumerate(ids):
            meta = {k: v for k, v in (metadatas[i] or {}).items()
                    if isinstance(v, (str, int, float, bool))}
            ops.append({"index": {"_index": self._index, "_id": _id}})
            ops.append({"text": documents[i], **meta})
        if ops:
            self._es.bulk(operations=ops, refresh=True)

    def sync_delete(self, where: dict) -> None:
        self._es.delete_by_query(index=self._index, query={"bool": {"filter": to_es_filter(where)}})

    def search(self, query: str, top_k: int, where: dict | None, rev: int) -> list[dict]:
        body = {
            "size": top_k,
            "query": {"bool": {
                "must": [{"multi_match": {"query": query, "fields": ["text^2", "title"]}}],
                "filter": to_es_filter(where),
            }},
        }
        res = self._es.search(index=self._index, body=body)
        out = []
        for hit in res["hits"]["hits"]:
            src = hit["_source"]
            text = src.pop("text", "")
            out.append({"id": hit["_id"], "text": text, "metadata": src,
                        "score": float(hit["_score"])})
        return out

    def count(self) -> int:
        try:
            return int(self._es.count(index=self._index)["count"])
        except Exception:
            return 0


_BACKEND = None
_LOCK = threading.Lock()


def get_backend(fetcher):
    """按配置返回关键词后端；配置 ES 但不可用时回退内置 BM25"""
    global _BACKEND
    with _LOCK:
        if _BACKEND is not None:
            return _BACKEND
        if settings.KEYWORD_BACKEND.lower() in ("elasticsearch", "es"):
            try:
                _BACKEND = ElasticsearchKeyword(settings.ES_URL, settings.ES_INDEX)
                _STATUS.update(backend="elasticsearch", fallback_reason="")
                return _BACKEND
            except Exception as e:
                _STATUS.update(backend="builtin",
                               fallback_reason=f"Elasticsearch 不可用（{type(e).__name__}），已回退内置 BM25")
        _BACKEND = BuiltinBM25(fetcher)
        _STATUS.update(backend="builtin")
        return _BACKEND


def status() -> dict:
    return {
        "configured": settings.KEYWORD_BACKEND,
        "active": _STATUS.get("backend"),
        "fallback_reason": _STATUS.get("fallback_reason", ""),
        "es_url": settings.ES_URL if settings.KEYWORD_BACKEND.lower() in ("elasticsearch", "es") else "",
    }
