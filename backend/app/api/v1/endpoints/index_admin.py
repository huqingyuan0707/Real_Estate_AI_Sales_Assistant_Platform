"""索引管理接口：版本查看 / 换模型重建 / 快照回滚（需 kb 权限）

对齐企业级 RAG 文档第三节「企业级必备」：嵌入模型可替换、索引版本可回滚、支持增量更新。
增量同步端点见 /documents/sync（按 SHA256 指纹跳过未变更文件）。
"""
from fastapi import APIRouter, Depends

from app.core.rbac import get_current_user, require_perm
from app.core.responses import fail, ok
from app.core.exceptions import ErrorCode
from app.schemas.requests import IndexRebuildRequest, IndexRollbackRequest
from app.services import index_admin, rag

router = APIRouter()


@router.get("/versions", dependencies=[Depends(require_perm("kb"))])
def index_versions():
    """索引版本历史 + 当前版本（模型 / 分块数 / 操作人 / 时间）"""
    data = index_admin.versions()
    return ok({
        "current": data.get("current") or {
            "revision": rag.kb_revision(), "embed_model": None, "chunks": rag.kb_count(),
        },
        "history": data.get("history") or [],
        "backups": index_admin.list_backups(),
    })


@router.post("/rebuild", dependencies=[Depends(require_perm("kb"))])
def index_rebuild(body: IndexRebuildRequest, user: dict = Depends(get_current_user)):
    """换嵌入模型整库重建（重建前自动快照，可用返回的 backup 名回滚）

    注意：重建会重新向量化全部已入库文本，模型首次加载可能耗时较长。
    """
    try:
        result = index_admin.rebuild(body.embed_model, username=user["username"])
    except Exception as e:
        return fail(ErrorCode.INTERNAL_ERROR, f"重建失败：{type(e).__name__}: {str(e)[:160]}")
    if not result.get("rebuilt"):
        return ok(result, result.get("message", "无需重建"))
    return ok(result, f"已用 {result['embed_model']} 重建 {result['rebuilt']} 个分块，原索引快照：{result['backup']}")


@router.post("/rollback", dependencies=[Depends(require_perm("kb"))])
def index_rollback(body: IndexRollbackRequest, user: dict = Depends(get_current_user)):
    """回滚到指定索引快照（原样恢复向量，无需重新编码）"""
    try:
        result = index_admin.rollback(body.backup, username=user["username"])
    except FileNotFoundError as e:
        return fail(ErrorCode.NOT_FOUND, str(e), 404)
    except Exception as e:
        return fail(ErrorCode.INTERNAL_ERROR, f"回滚失败：{type(e).__name__}: {str(e)[:160]}")
    return ok(result, f"已回滚 {result['restored']} 个分块（模型 {result['embed_model']}）")
