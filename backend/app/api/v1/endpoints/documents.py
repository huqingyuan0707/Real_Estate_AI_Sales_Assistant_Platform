"""知识库接口：列表 / 上传入库（治理标注 + 版本控制）/ 批量导入（异步任务）/ 试搜

- 上传治理标注：密级（公开/内部/机密）、归属部门、审核状态（草稿/已发布/已归档）、生效期
- Owner 取当前登录用户（不再硬编码），文档注册表持久化到 backend/data/documents.json，可回溯
- 同名文档重复上传按 11.2 版本控制策略升版本：旧版 deprecated 并下线旧向量，检索只命中新版
- 访问控制：上传/删除需 kb 权限；试搜按当前用户的可见范围过滤（检索前 + 检索后双阶段）
"""
import asyncio
import hashlib
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, UploadFile

from app.config import settings
from app.core.exceptions import ErrorCode
from app.core.rbac import get_current_user, require_perm
from app.core.responses import fail, ok
from app.core.user_context import current_user
from app.mock_data import DOCUMENTS
from app.schemas.requests import DocReviewRequest, DocumentSearchRequest
from app.services import governance, index_admin, ingest, rag, task_center
from app.services import user_store

router = APIRouter()

_REGISTRY_PATH = Path(__file__).resolve().parents[4] / "data" / "documents.json"
_REG_LOCK = threading.Lock()
_uploaded: list[dict] = []

CATEGORY_BY_EXT = {".pdf": "PDF", ".docx": "Word", ".xlsx": "Excel", ".txt": "TXT", ".md": "Markdown"}


# ---------------- 注册表持久化 ----------------

def _save_registry() -> None:
    _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = f"{_REGISTRY_PATH}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_uploaded, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _REGISTRY_PATH)


def _load_registry() -> None:
    global _uploaded
    try:
        with open(_REGISTRY_PATH, encoding="utf-8") as f:
            _uploaded = json.load(f)
    except Exception:
        _uploaded = []


_load_registry()


# ---------------- 治理参数解析 ----------------

def _parse_ts(value: str | None) -> float:
    """「2026-09-10」/「2026-09-10 12:00」→ epoch 秒；空值 → 0（不限）"""
    if not value or not value.strip():
        return 0.0
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).timestamp()
        except ValueError:
            continue
    return 0.0


def _owner_label() -> tuple[str, str]:
    """返回 (登录名, 展示名)；Owner 归属用于知识运营追责"""
    username = current_user() or ""
    user = user_store.get(username) if username else None
    return username, (user or {}).get("name", username or "未知")


def _next_version(name: str) -> tuple[int, list[dict]]:
    """返回 (下一个版本号, 该文件名现有全部版本记录)"""
    existing = [d for d in _uploaded if d["name"] == name]
    return len(existing) + 1, existing


def _register_doc(name: str, content: bytes, category: str, *, username: str, display: str,
                  security_level: str, dept_id: str, review_status: str,
                  effective_ts: float, expire_ts: float) -> dict:
    """注册新版本文档记录（processing），并按 11.2 下线旧版本"""
    with _REG_LOCK:
        ver, existing = _next_version(name)
        doc = {
            "id": f"up-{int(time.time() * 1000)}-{ver}",
            "name": name,
            "type": category,
            "size": f"{len(content) / 1024 / 1024:.1f} MB",
            "sha256": hashlib.sha256(content).hexdigest(),
            "status": "processing",
            "version": f"v{ver}",
            "updatedAt": time.strftime("%Y-%m-%d %H:%M"),
            "chunks": 0,
            "uploader": display,
            "owner": username,
            # ---- 治理标签 ----
            "security_level": security_level,
            "dept_id": dept_id,
            "review_status": review_status,
            "effective_at": time.strftime("%Y-%m-%d", time.localtime(effective_ts)) if effective_ts else "",
            "expire_at": time.strftime("%Y-%m-%d", time.localtime(expire_ts)) if expire_ts else "",
            "is_active": True,
            "superseded_by": None,
            "deprecated_at": None,
        }
        for old in existing:
            if old.get("is_active"):
                old["is_active"] = False
                old["status"] = "deprecated"
                old["superseded_by"] = doc["id"]
                old["deprecated_at"] = time.strftime("%Y-%m-%d %H:%M")
        _uploaded.insert(0, doc)
        _save_registry()
        return doc


def _do_ingest(doc: dict, path: str, name: str, category: str, ctx: dict, gov: dict) -> None:
    """入库链（同步阻塞，线程池执行）：解析/分块/治理元数据/bge 向量化/写 Chroma"""
    doc["status"] = "processing"
    try:
        stat = ingest.ingest_file(
            path, name, category, ctx=ctx,
            security_level=gov.get("security_level"), dept_id=gov.get("dept_id"),
            review_status=gov.get("review_status"), effective_ts=gov.get("effective_ts", 0.0),
            expire_ts=gov.get("expire_ts", 0.0), doc_version=gov.get("doc_version", 1),
            title=name,
        )
        doc["chunks"] = stat["chunks"]
        doc["status"] = "active"
    except Exception as e:  # 解析失败标记失效，便于前端提示
        doc["status"] = "inactive"
        doc["error"] = str(e)[:200]
    finally:
        with _REG_LOCK:
            _save_registry()


def _gov_params(security_level: str | None, dept_id: str | None, review_status: str | None,
                effective_at: str | None, expire_at: str | None, version: int) -> dict:
    return {
        "security_level": governance.normalize_level(security_level),
        "dept_id": (dept_id or "").strip(),
        "review_status": governance.normalize_review(review_status),
        "effective_ts": _parse_ts(effective_at),
        "expire_ts": _parse_ts(expire_at),
        "doc_version": version,
    }


# ---------------- 接口 ----------------

@router.get("")
def list_documents():
    """mock 种子数据 + 真实上传文档（含版本链与治理标签）合并列表"""
    return ok([*DOCUMENTS, *_uploaded])


@router.get("/governance")
def governance_overview():
    """治理总览：密级/部门/审核态分布 + 可选标签值（供上传表单与运营看板）"""
    return ok({
        "stats": rag.governance_stats(),
        "options": {
            "security_levels": [{"value": k, "label": v} for k, v in governance.LEVEL_NAMES.items()],
            "review_status": [{"value": k, "label": v} for k, v in governance.REVIEW_NAMES.items()],
            "depts": sorted({(u.get("workspace") or "") for u in user_store.list_users()} - {""}),
        },
    })


@router.post("/upload", dependencies=[Depends(require_perm("kb"))])
async def upload_document(
    background: BackgroundTasks,
    file: UploadFile,
    category: str | None = Form(None),
    security_level: str | None = Form(None),
    dept_id: str | None = Form(None),
    review_status: str | None = Form(None),
    effective_at: str | None = Form(None),
    expire_at: str | None = Form(None),
):
    """上传 → 落盘 → 后台执行入库链（带治理标注）；同名文件自动升版本并下线旧版（11.2）"""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ingest.SUPPORTED_EXT:
        return ok({"status": "unsupported", "filename": file.filename},
                  f"暂不支持 {ext} 格式，支持：PDF/Word/Excel/TXT/MD")

    content = await file.read()
    name = file.filename or "unnamed"
    # 增量判断：与当前**成功入库**版本内容一致（SHA256 相同）才跳过；
    # processing / inactive（解析失败或后端重启丢失任务）不跳过，允许重试
    fingerprint = hashlib.sha256(content).hexdigest()
    current = next((d for d in _uploaded
                    if d["name"] == name and d.get("is_active") and d.get("status") == "active"), None)
    if current and current.get("sha256") == fingerprint:
        return ok({"status": "unchanged", "filename": name, "version": current["version"]},
                  "内容与当前版本一致（SHA256 相同），已跳过重复入库")
    # 同名旧版本在库 → 先清旧向量，保证检索只命中新版本
    _, existing = _next_version(name)
    if existing:
        rag.delete_by_source(name)
    path = ingest.save_upload(name, content)
    cat = category or CATEGORY_BY_EXT.get(ext, "OTHER")

    username, display = _owner_label()
    ctx = governance.access_context()
    gov = _gov_params(security_level, dept_id, review_status, effective_at, expire_at, len(existing) + 1)
    doc = _register_doc(name, content, cat, username=username, display=display,
                        security_level=gov["security_level"], dept_id=gov["dept_id"],
                        review_status=gov["review_status"], effective_ts=gov["effective_ts"],
                        expire_ts=gov["expire_ts"])
    background.add_task(_do_ingest, doc, path, name, cat, ctx, gov)
    superseded = "，旧版本已自动归档" if existing else ""
    review_hint = "（草稿态，不参与检索）" if gov["review_status"] != "published" else ""
    return ok({"status": "accepted", "filename": name, "version": doc["version"],
               "size_kb": len(content) // 1024,
               "security_level": gov["security_level"], "review_status": gov["review_status"]},
              f"上传成功（{doc['version']}）{review_hint}，正在解析入库{superseded}")


@router.post("/batch-import", dependencies=[Depends(require_perm("kb"))])
async def batch_import(files: list[UploadFile] = File(...),
                       security_level: str | None = Form(None),
                       dept_id: str | None = Form(None),
                       review_status: str | None = Form(None)):
    """批量导入（异步任务，对齐 5.2）：返回 task_id，进度经 /tasks/{task_id}/status|stream 查询"""
    if not files:
        return fail(ErrorCode.PARAM_INVALID, "请至少选择一个文件", 400)
    blobs: list[tuple[str, bytes]] = []
    for f in files:
        blobs.append((f.filename or "unnamed", await f.read()))

    rec = task_center.create("batch_import", f"批量导入 {len(blobs)} 份文档",
                             {"filenames": [n for n, _ in blobs]})
    task_id = rec["task_id"]
    username, display = _owner_label()
    ctx = governance.access_context()
    base_gov = _gov_params(security_level, dept_id, review_status, None, None, 1)

    async def _runner():
        ok_items, fail_items = [], []
        total = len(blobs)
        for i, (name, content) in enumerate(blobs):
            task_center.set_progress(task_id, int(i / total * 100), f"导入 {name}（{i + 1}/{total}）")
            try:
                ext = os.path.splitext(name)[1].lower()
                if ext not in ingest.SUPPORTED_EXT:
                    raise ValueError(f"暂不支持 {ext} 格式")
                _, existing = _next_version(name)
                if existing:
                    rag.delete_by_source(name)
                path = ingest.save_upload(name, content)
                cat = CATEGORY_BY_EXT.get(ext, "OTHER")
                gov = {**base_gov, "doc_version": len(existing) + 1}
                doc = _register_doc(name, content, cat, username=username, display=display,
                                    security_level=gov["security_level"], dept_id=gov["dept_id"],
                                    review_status=gov["review_status"], effective_ts=0.0, expire_ts=0.0)
                await asyncio.to_thread(_do_ingest, doc, path, name, cat, ctx, gov)
                if doc["status"] == "active":
                    ok_items.append({"name": name, "version": doc["version"], "chunks": doc["chunks"]})
                else:
                    fail_items.append({"name": name, "error": doc.get("error", "解析失败")})
            except Exception as e:
                fail_items.append({"name": name, "error": str(e)[:120]})
            await asyncio.sleep(0)  # 让出事件循环，保证进度可查询/任务可取消
        return {"success": len(ok_items), "failed": len(fail_items), "items": ok_items, "fail_items": fail_items}

    task_center.attach(task_id, _runner)
    return ok({
        "task_id": task_id,
        "status": "pending",
        "total": len(blobs),
        "estimated_seconds": len(blobs) * 3,
        "poll_url": f"/api/v1/tasks/{task_id}/status",
        "stream_url": f"/api/v1/tasks/{task_id}/stream",
    }, "批量导入任务已提交")


@router.get("/{doc_id}/status")
def document_status(doc_id: str):
    doc = next((d for d in _uploaded if d["id"] == doc_id), None)
    if not doc:
        return ok(None, "文档不存在（mock 数据无状态跟踪）")
    return ok(doc)


@router.post("/search")
def search_documents(body: DocumentSearchRequest):
    """知识库试搜：双路召回 + RRF + 重排，按当前用户可见范围过滤，返回片段与相关度"""
    if not body.query.strip():
        return ok([])
    ctx = governance.access_context()
    hits, _rejected, _trace = rag.retrieve(body.query, ctx)
    return ok([{
        "doc": h["metadata"]["source"],
        "page": h["metadata"].get("page", 1),
        "section": h["metadata"].get("section", ""),
        "score": round(h["score"] * 100),
        "snippet": f"…{h['text'][:120]}…",
        "category": h["metadata"].get("category", ""),
        "security_level": h["metadata"].get("security_level", ""),
        "dept_id": h["metadata"].get("dept_id", ""),
        "routes": h.get("routes", 1),
    } for h in hits])


@router.delete("/{name}", dependencies=[Depends(require_perm("kb"))])
def delete_document(name: str):
    """按源文件删除：删除 Chroma 中该文件全部向量 + 移除注册表记录"""
    deleted_chunks = rag.delete_by_source(name)
    global_removed = any(d["name"] == name for d in _uploaded)
    with _REG_LOCK:
        _uploaded[:] = [d for d in _uploaded if d["name"] != name]
        _save_registry()
    return ok({"name": name, "deleted_chunks": deleted_chunks, "removed": True},
              f"已删除《{name}》及 {deleted_chunks} 个向量块" if deleted_chunks else "文档不在向量索引中，已移除记录")


@router.post("/{doc_id}/review", dependencies=[Depends(require_perm("kb"))])
def review_document(doc_id: str, body: DocReviewRequest, user: dict = Depends(get_current_user)):
    """知识审核（生命周期：创建 → 审核 → 发布 / 驳回 → 归档）

    审核结果会同步写入向量元数据：草稿态不参与检索，发布后立即参与，归档后退出检索。
    """
    doc = next((d for d in _uploaded if d["id"] == doc_id), None)
    if not doc:
        return fail(ErrorCode.NOT_FOUND, "文档不存在", 404)
    target = {"approve": "published", "reject": "draft", "archive": "archived"}[body.action]
    doc["review_status"] = target
    doc["review_status_label"] = governance.REVIEW_NAMES.get(target, target)
    doc["review_comment"] = body.comment
    doc["reviewed_by"] = user["username"]
    doc["reviewed_at"] = time.strftime("%Y-%m-%d %H:%M")
    updated = rag.update_source_meta(doc["name"], {"review_status": target})
    with _REG_LOCK:
        _save_registry()
    index_admin.record(f"review:{body.action}", username=user["username"])
    label = governance.REVIEW_NAMES.get(target, target)
    hint = "（草稿不参与检索）" if target == "draft" else ("（已退出检索）" if target == "archived" else "")
    return ok({"doc_id": doc_id, "review_status": target, "updated_chunks": updated},
              f"《{doc['name']}》已{label}{hint}，同步更新 {updated} 个分块")


@router.get("/quality", dependencies=[Depends(require_perm("kb"))])
def quality_report():
    """知识质量校验（文档第一节：完整性 / 准确性 / 时效性 / 一致性）

    检查项：空文档/解析失败、已过期、长期未更新、草稿未发布、内容重复（指纹一致）、治理标签缺失。
    """
    now = time.time()
    issues: dict[str, list[dict]] = {k: [] for k in
                                     ("empty", "expired", "stale", "unpublished", "duplicate", "missing_gov")}
    seen: dict[str, str] = {}
    stale_days = 180

    for d in _uploaded:
        name = d["name"]
        if d.get("status") == "inactive" or not d.get("chunks"):
            issues["empty"].append({"name": name, "detail": d.get("error", "未产生分块或解析失败")})
        exp = _parse_ts(d.get("expire_at"))
        if exp and exp < now:
            issues["expired"].append({"name": name, "expire_at": d.get("expire_at")})
        ts = d.get("updatedAt")
        if ts:
            try:
                age = (now - datetime.strptime(ts, "%Y-%m-%d %H:%M").timestamp()) / 86400
                if age > stale_days:
                    issues["stale"].append({"name": name, "days": int(age)})
            except ValueError:
                pass
        if d.get("review_status") == "draft":
            issues["unpublished"].append({"name": name, "version": d.get("version")})
        fp = d.get("sha256")
        if fp:
            if fp in seen:
                issues["duplicate"].append({"name": name, "same_as": seen[fp]})
            else:
                seen[fp] = name
        if not d.get("owner") or not d.get("security_level"):
            issues["missing_gov"].append({"name": name})

    total_docs = len(_uploaded)
    total_issues = sum(len(v) for v in issues.values())
    health = round(max(0.0, 1 - total_issues / max(1, total_docs * 2)), 3)
    return ok({
        "doc_count": total_docs,
        "issue_count": total_issues,
        "health_score": health,
        "issues": issues,
        "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "rule": f"时效性阈值 {stale_days} 天；健康度 = 1 - 问题数 / (文档数 × 2)",
    })


@router.post("/sync", dependencies=[Depends(require_perm("kb"))])
async def sync_documents():
    """增量同步：扫描上传目录，按 SHA256 指纹只处理新增/变更文件（跳过未变更，避免全量重建）"""
    upload_dir = Path(settings.RAG_UPLOAD_DIR)
    if not upload_dir.exists():
        return ok({"added": [], "updated": [], "unchanged": 0, "failed": []}, "上传目录为空，无需同步")

    known = {d["name"]: d.get("sha256", "") for d in _uploaded
             if d.get("is_active") and d.get("status") == "active"}
    username, display = _owner_label()
    added, updated, failed = [], [], []
    unchanged = 0

    for p in sorted(upload_dir.glob("*")):
        if not p.is_file():
            continue
        raw = p.name.split("_", 1)[1] if "_" in p.name else p.name
        ext = os.path.splitext(raw)[1].lower()
        if ext not in ingest.SUPPORTED_EXT:
            continue
        try:
            fp = index_admin.file_fingerprint(p)
        except Exception as e:
            failed.append({"name": raw, "error": str(e)[:120]})
            continue
        if known.get(raw) == fp:
            unchanged += 1
            continue
        cat = CATEGORY_BY_EXT.get(ext, "OTHER")
        is_update = raw in known
        if is_update:
            rag.delete_by_source(raw)
        try:
            stat = await asyncio.to_thread(ingest.ingest_file, str(p), raw, cat)
            doc = _register_doc(raw, p.read_bytes(), cat, username=username, display=display,
                                security_level="internal", dept_id="", review_status="published",
                                effective_ts=0.0, expire_ts=0.0)
            doc["chunks"] = stat["chunks"]
            doc["status"] = "active"
            with _REG_LOCK:
                _save_registry()
            (updated if is_update else added).append({"name": raw, "chunks": stat["chunks"]})
        except Exception as e:
            failed.append({"name": raw, "error": str(e)[:120]})

    index_admin.record("sync", username=username)
    changed = len(added) + len(updated)
    return ok({"added": added, "updated": updated, "unchanged": unchanged, "failed": failed},
              f"增量同步完成：新增 {len(added)}、更新 {len(updated)}、未变更 {unchanged}"
              if changed else f"无变更（{unchanged} 个文件指纹一致，已跳过）")


@router.get("/stats")
def rag_stats():
    """知识库统计：总块数 / 已索引源文件清单 / 模型配置 / 治理分布"""
    sources = rag.list_sources()
    return ok({
        "kb_chunks": rag.kb_count(),
        "doc_count": len(sources),
        "sources": sources,
        "governance": rag.governance_stats(),
        "upload_dir": settings.RAG_UPLOAD_DIR,
        "embed_model": settings.RAG_EMBED_MODEL,
        "rerank_model": settings.RAG_RERANK_MODEL,
    })
