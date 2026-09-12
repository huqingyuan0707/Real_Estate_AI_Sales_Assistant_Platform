"""知识治理与访问控制（企业级 RAG 第一层：先治理，再 RAG）

治理维度（每条知识、每个分块都携带）：
租户 tenant_id / 密级 security_level / 部门 dept_id / 审核状态 review_status
/ Owner owner / 版本 doc_version / 生效期 effective_ts ~ expire_ts / 标题 title

访问控制模型（对齐文档第六节：权限过滤在检索与生成两阶段都做）：
- 密级：public 公开、internal 内部（默认）、confidential 机密
  admin 可见全部；manager / member 可见 public + internal
- 部门：知识 dept_id 为空 = 全公司可见；非空 = 同部门可见，admin/manager 跨部门可见
- 审核：draft 草稿与 archived 归档一律不进检索，只有 published 参与召回
- 生效期：effective_ts 未到或 expire_ts 已过 → 不参与检索（时效性）

双阶段实现：
1) 检索前硬过滤 —— Chroma where（租户 + 审核态 + 密级，可索引字段）
2) 检索后精过滤 —— 应用层校验部门与生效期（见 filter_hits），命中但越权的一律丢弃并计入告警
"""
import time

from app.core.user_context import current_user
from app.services import user_store

# ---------------- 常量 ----------------

LEVELS = ("public", "internal", "confidential")
LEVEL_NAMES = {"public": "公开", "internal": "内部", "confidential": "机密"}
DEFAULT_LEVEL = "internal"

REVIEW_STATUS = ("draft", "published", "archived")
REVIEW_NAMES = {"draft": "草稿", "published": "已发布", "archived": "已归档"}
DEFAULT_REVIEW = "published"

# 角色 → 可访问密级
ROLE_LEVELS: dict[str, tuple[str, ...]] = {
    "admin": LEVELS,
    "manager": ("public", "internal"),
    "member": ("public", "internal"),
}
# 可跨部门访问的角色（其余角色只能看本部门 + 全公司知识）
CROSS_DEPT_ROLES = ("admin", "manager")

# 存量数据回填默认值（治理字段上线前入库的向量）
DEFAULT_META = {
    "tenant_id": "default",
    "dept_id": "",
    "security_level": DEFAULT_LEVEL,
    "review_status": DEFAULT_REVIEW,
    "owner": "",
    "doc_version": 1,
    "effective_ts": 0.0,
    "expire_ts": 0.0,
    "title": "",
}


def allowed_levels(role: str) -> tuple[str, ...]:
    return ROLE_LEVELS.get(role, ("public", "internal"))


# ---------------- 当前访问上下文（从 Token 用户推导，不可被请求体伪造） ----------------

def access_context(tenant_id: str = "default") -> dict:
    """解析当前用户的可见范围：角色 / 部门 / 可访问密级 / 是否跨部门"""
    username = current_user() or ""
    user = user_store.get(username) if username else None
    role = (user or {}).get("role", "member")
    return {
        "username": username,
        "name": (user or {}).get("name", username),
        "role": role,
        "dept": (user or {}).get("workspace", "") or "",
        "tenant_id": tenant_id or "default",
        "levels": allowed_levels(role),
        "cross_dept": role in CROSS_DEPT_ROLES,
    }


# ---------------- 阶段一：Chroma 硬过滤条件 ----------------

def build_where(ctx: dict) -> dict:
    """检索前硬过滤：租户 + 审核态 + 密级（均为可索引的等值/集合条件）"""
    return {"$and": [
        {"tenant_id": ctx.get("tenant_id", "default")},
        {"review_status": DEFAULT_REVIEW},
        {"security_level": {"$in": list(ctx.get("levels") or allowed_levels("member"))}},
    ]}


# ---------------- 阶段二：应用层精过滤（部门 / 生效期） ----------------

def _dept_ok(meta: dict, ctx: dict) -> bool:
    dept = (meta.get("dept_id") or "").strip()
    if not dept or ctx.get("cross_dept"):
        return True
    return dept == (ctx.get("dept") or "").strip()


def _time_ok(meta: dict, now: float) -> bool:
    eff = float(meta.get("effective_ts") or 0)
    exp = float(meta.get("expire_ts") or 0)
    if eff and eff > now:
        return False
    if exp and exp < now:
        return False
    return True


def check_hit(meta: dict, ctx: dict, now: float | None = None) -> tuple[bool, str]:
    """单条片段的可见性判定，返回 (是否可见, 拒绝原因)"""
    now = now or time.time()
    if meta.get("review_status", DEFAULT_REVIEW) != DEFAULT_REVIEW:
        return False, "未发布"
    if meta.get("security_level", DEFAULT_LEVEL) not in (ctx.get("levels") or ()):
        return False, "密级不足"
    if str(meta.get("tenant_id", "default")) != str(ctx.get("tenant_id", "default")):
        return False, "租户不匹配"
    if not _dept_ok(meta, ctx):
        return False, "跨部门"
    if not _time_ok(meta, now):
        return False, "不在生效期"
    return True, ""


def filter_hits(hits: list[dict], ctx: dict) -> tuple[list[dict], list[dict]]:
    """检索后精过滤：返回 (可见片段, 被拦截片段)。被拦截记录原因，供越权告警与审计"""
    kept: list[dict] = []
    blocked: list[dict] = []
    now = time.time()
    for h in hits:
        allowed, reason = check_hit(h.get("metadata") or {}, ctx, now)
        if allowed:
            kept.append(h)
        else:
            blocked.append({**h, "blocked_reason": reason})
    return kept, blocked


# ---------------- 分块治理元数据 ----------------

def chunk_meta(*, source: str, category: str, page: int, chunk_index: int, ctx: dict,
               security_level: str | None = None, dept_id: str | None = None,
               review_status: str | None = None, effective_ts: float = 0.0,
               expire_ts: float = 0.0, doc_version: int = 1, title: str = "",
               section: str = "", parent_id: str = "") -> dict:
    """构造单个分块的完整治理元数据（写入 Chroma，检索时按此过滤）"""
    return {
        "source": source,
        "category": category,
        "page": int(page),
        "chunk_index": int(chunk_index),
        "section": section or "",
        "parent_id": parent_id or "",
        "title": title or source,
        "tenant_id": ctx.get("tenant_id", "default"),
        "dept_id": (dept_id or "").strip(),
        "security_level": security_level if security_level in LEVELS else DEFAULT_LEVEL,
        "review_status": review_status if review_status in REVIEW_STATUS else DEFAULT_REVIEW,
        "owner": ctx.get("username", ""),
        "doc_version": int(doc_version),
        "effective_ts": float(effective_ts or 0),
        "expire_ts": float(expire_ts or 0),
    }


def normalize_level(value: str | None) -> str:
    return value if value in LEVELS else DEFAULT_LEVEL


def normalize_review(value: str | None) -> str:
    return value if value in REVIEW_STATUS else DEFAULT_REVIEW
