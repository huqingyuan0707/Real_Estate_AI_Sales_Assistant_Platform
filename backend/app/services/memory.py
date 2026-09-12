"""记忆服务：短期会话记忆 + 长期用户记忆

设计要点（对应需求）：
- 短期记忆：仅保存当前会话近期消息与任务状态；用「滑动窗口 + 滚动摘要 + Token 预算」控制长度
- 长期记忆：只保存用户明确授权且稳定的信息（偏好/常用项目等），支持查看、修改、删除
- 业务事实不进记忆：楼盘价格/政策等实时信息一律由系统接口或 RAG 检索获取，不依赖模型记忆
- 隔离：短期与长期记忆均按 (tenant_id, user_id) 隔离
- 敏感信息：写入前做分类与敏感检测，敏感内容强制设置过期时间，读取时惰性清理
- 授权：写入长期记忆必须显式 authorized=True；否则进入 pending 状态，不会注入任何对话

存储：
- 短期：进程内存（生产可迁移 Redis），key=(tenant, user, thread)
- 长期：data/memory_store.json（生产可迁移 MySQL），按租户/用户分桶
"""
import json
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import settings

# ---------------------------------------------------------------------------
# Token 估算（中文保守口径：1 字符 ≈ 0.75 token）
# ---------------------------------------------------------------------------


def est_tokens(text: str) -> int:
    return max(1, (len(text) * 3 + 3) // 4)


# ---------------------------------------------------------------------------
# 分类与敏感检测（写入长期记忆前的强制的分类步骤）
# ---------------------------------------------------------------------------

_SENSITIVE_PATTERNS = (
    ("身份证", re.compile(r"\b\d{17}[\dXx]\b")),
    ("手机号", re.compile(r"\b1[3-9]\d{9}\b")),
    ("银行卡", re.compile(r"\b\d{13,19}\b")),
)

_CATEGORY_RULES = (
    ("preference", ("喜欢", "偏好", "习惯", "倾向", "爱好", "中意", "偏好于", "想要")),
    ("project", ("楼盘", "项目", "小区", "户型", "关注")),
)


def classify_content(content: str) -> tuple[str, bool]:
    """返回 (分类, 是否敏感)。分类规则：偏好 / 项目 / fact(其他稳定信息)。"""
    sensitive = any(p.search(content) for _, p in _SENSITIVE_PATTERNS)
    for cat, words in _CATEGORY_RULES:
        if any(w in content for w in words):
            return cat, sensitive
    return "fact", sensitive


# ---------------------------------------------------------------------------
# 短期记忆（会话内）：窗口 + 摘要 + Token 预算
# ---------------------------------------------------------------------------

_SHORT: dict[tuple[str, str, str], dict] = {}
_SHORT_LOCK = threading.Lock()

# 短期记忆落盘：进程重启后历史仍可恢复（生产可迁移 Redis）。
# 键用 \x1f 连接 (tenant, user, thread)，取值时裁剪到窗口大小。
_SHORT_PATH = Path(settings.MEM_STORE_PATH).parent / "short_memory.json"
_SHORT_SEP = "\x1f"
_SHORT_LOADED = False


def _persist_short() -> None:
    """锁内调用：将全量短期记忆落盘（失败不影响主链路）"""
    try:
        data = {_SHORT_SEP.join(k): v for k, v in _SHORT.items()}
        _SHORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SHORT_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _restore_short() -> None:
    """锁内调用：进程首次访问时从磁盘恢复（历史 bug：纯内存，重启即丢全部对话历史）"""
    global _SHORT_LOADED
    if _SHORT_LOADED:
        return
    _SHORT_LOADED = True
    if not _SHORT_PATH.exists():
        return
    try:
        data = json.loads(_SHORT_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(data, dict):
        return
    for k, v in data.items():
        parts = k.split(_SHORT_SEP)
        if len(parts) == 3 and isinstance(v, dict) and isinstance(v.get("messages"), list):
            _SHORT[(parts[0], parts[1], parts[2])] = {
                "summary": str(v.get("summary", "")),
                "messages": v["messages"][-settings.MEM_WINDOW:],
                "task": v.get("task"),
            }


def _short_key(tenant_id: str, user_id: str, thread_id: str) -> tuple[str, str, str]:
    return (tenant_id, user_id, thread_id or "default")


def _new_session() -> dict:
    return {"summary": "", "messages": [], "task": None}


def _session_tokens(sess: dict) -> int:
    return est_tokens(sess["summary"]) + sum(est_tokens(m["content"]) for m in sess["messages"])


def add_message(tenant_id: str, user_id: str, thread_id: str, role: str, content: str) -> None:
    """追加一条消息并按 窗口/预算 裁剪（超限的早期内容滚动进摘要）。"""
    with _SHORT_LOCK:
        _restore_short()
        sess = _SHORT.setdefault(_short_key(tenant_id, user_id, thread_id), _new_session())
        sess["messages"].append({
            "role": role,
            "content": content,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        # 1) 条数窗口
        overflow = []
        while len(sess["messages"]) > settings.MEM_WINDOW:
            overflow.append(sess["messages"].pop(0))
        # 2) Token 预算：仍超则继续把最旧的一半滚入摘要
        while sess["messages"] and _session_tokens(sess) > settings.MEM_TOKEN_BUDGET:
            half = max(1, len(sess["messages"]) // 2)
            overflow.extend(sess["messages"][:half])
            del sess["messages"][:half]
        if overflow:
            piece = "\n".join(f"{'用户' if m['role'] == 'user' else '助手'}: {m['content'][:200]}" for m in overflow)
            sess["summary"] = (sess["summary"] + "\n" + piece).strip()[-1500:]
        _persist_short()


def get_context(tenant_id: str, user_id: str, thread_id: str) -> tuple[str, list[dict]]:
    """返回 (滚动摘要, 窗口内消息)。供 Query 改写与 Prompt 组装使用。"""
    with _SHORT_LOCK:
        _restore_short()
        sess = _SHORT.get(_short_key(tenant_id, user_id, thread_id))
        if not sess:
            return "", []
        return sess["summary"], [dict(m) for m in sess["messages"]]


def set_task_state(tenant_id: str, user_id: str, thread_id: str, task: dict | None) -> None:
    """记录当前会话任务状态（如最近一次任务类型/阶段），仅限当前会话生命周期。"""
    with _SHORT_LOCK:
        _restore_short()
        sess = _SHORT.setdefault(_short_key(tenant_id, user_id, thread_id), _new_session())
        sess["task"] = task
        _persist_short()


def clear_short(tenant_id: str, user_id: str, thread_id: str) -> bool:
    with _SHORT_LOCK:
        _restore_short()
        removed = _SHORT.pop(_short_key(tenant_id, user_id, thread_id), None) is not None
        if removed:
            _persist_short()
        return removed


def short_stats() -> dict:
    with _SHORT_LOCK:
        _restore_short()  # 缺此行会漏算已落盘的历史会话（设置页显示 0 个活跃会话）
        sessions = len(_SHORT)
        msgs = sum(len(s["messages"]) for s in _SHORT.values())
    return {"active_sessions": sessions, "cached_messages": msgs}


def list_threads(tenant_id: str, user_id: str) -> list[dict]:
    """列出该用户的全部会话（历史列表用）：标题取首条用户提问，按最近活动倒序。

    历史 bug：/sessions 曾直接返回 mock 常量，真实会话永不出现，
    页面刷新后新建会话凭空消失（表现为"历史对话没有保存记录"）。
    """
    with _SHORT_LOCK:
        _restore_short()
        out = []
        for (tenant, user, thread_id), sess in _SHORT.items():
            if tenant != tenant_id or user != user_id:
                continue
            msgs = sess.get("messages") or []
            summary = sess.get("summary") or ""
            if not msgs and not summary:
                continue  # 空壳会话（只点了"新建"没提问）不进历史
            first_user = next((m["content"] for m in msgs if m.get("role") == "user"), "")
            title = (first_user or summary or "新对话").strip().replace("\n", " ")
            out.append({
                "thread_id": thread_id,
                "title": title[:20] + ("…" if len(title) > 20 else ""),
                "updated_at": (msgs[-1].get("ts") if msgs else "") or "",
                "count": len(msgs),
            })
        out.sort(key=lambda x: x["updated_at"], reverse=True)
        return out


# ---------------------------------------------------------------------------
# 长期记忆（跨会话）：授权写入 + 分类 + 敏感过期 + CRUD
# ---------------------------------------------------------------------------

_STORE_PATH = Path(settings.MEM_STORE_PATH)
_LONG_LOCK = threading.Lock()


class MemoryDenied(Exception):
    """写入被拒绝（未授权 / 敏感信息未设置过期时间）"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_store() -> dict:
    if not _STORE_PATH.exists():
        return {}
    try:
        return json.loads(_STORE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_store(store: dict) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")


def _bucket(store: dict, tenant_id: str, user_id: str) -> list:
    return store.setdefault(tenant_id, {}).setdefault(user_id, [])


def _purge_expired(entries: list) -> list:
    """惰性清理过期条目，返回存活列表。"""
    now = _now()
    alive = []
    for e in entries:
        exp = e.get("expires_at")
        if exp and datetime.fromisoformat(exp) <= now:
            continue
        alive.append(e)
    return alive


def add_long(tenant_id: str, user_id: str, content: str, category: str | None = None,
             authorized: bool = False, expires_days: int | None = None) -> dict:
    """写入长期记忆。规则：
    - 未授权 → pending 状态（authorized=False），永不注入对话，仅等用户确认
    - 敏感信息（手机号/身份证/银行卡）必须带过期时间，否则拒绝写入
    - 分类：显式指定优先，否则规则自动分类
    """
    content = content.strip()
    if not content:
        raise MemoryDenied("记忆内容不能为空")
    auto_cat, sensitive = classify_content(content)
    category = category or auto_cat
    if sensitive and not expires_days:
        raise MemoryDenied("检测到敏感信息（手机号/身份证/银行卡），必须设置过期时间后才能写入长期记忆")

    entry = {
        "id": uuid.uuid4().hex[:12],
        "category": category,
        "content": content,
        "authorized": bool(authorized),
        "sensitive": sensitive,
        "expires_at": (_now() + timedelta(days=expires_days)).isoformat() if expires_days else None,
        "created_at": _now().isoformat(),
        "updated_at": _now().isoformat(),
    }
    with _LONG_LOCK:
        store = _load_store()
        _bucket(store, tenant_id, user_id).append(entry)
        _save_store(store)
    return entry


def list_long(tenant_id: str, user_id: str) -> list[dict]:
    """查看本用户全部长期记忆（含 pending；已过期条目惰性清除）。"""
    with _LONG_LOCK:
        store = _load_store()
        entries = _purge_expired(_bucket(store, tenant_id, user_id))
        _bucket(store, tenant_id, user_id)[:] = entries
        _save_store(store)
        return [dict(e) for e in entries]


def effective_long(tenant_id: str, user_id: str) -> list[dict]:
    """可注入对话的长期记忆：已授权 且 未过期。"""
    return [e for e in list_long(tenant_id, user_id) if e["authorized"]]


def update_long(tenant_id: str, user_id: str, memory_id: str,
                content: str | None = None, category: str | None = None,
                authorized: bool | None = None, expires_days: int | None = None) -> dict | None:
    """修改 / 授权确认。内容修改后重新做分类与敏感检测。"""
    with _LONG_LOCK:
        store = _load_store()
        for e in _bucket(store, tenant_id, user_id):
            if e["id"] == memory_id:
                if content is not None:
                    _, sensitive = classify_content(content)
                    e["content"] = content.strip()
                    e["sensitive"] = sensitive
                if category is not None:
                    e["category"] = category
                if authorized is not None:
                    e["authorized"] = authorized
                if expires_days is not None:
                    e["expires_at"] = (_now() + timedelta(days=expires_days)).isoformat()
                # 修改后仍是敏感且无过期时间 → 强制兜底 30 天
                if e["sensitive"] and not e.get("expires_at"):
                    e["expires_at"] = (_now() + timedelta(days=settings.MEM_SENSITIVE_TTL_DAYS)).isoformat()
                e["updated_at"] = _now().isoformat()
                _save_store(store)
                return dict(e)
    return None


def delete_long(tenant_id: str, user_id: str, memory_id: str) -> bool:
    with _LONG_LOCK:
        store = _load_store()
        entries = _bucket(store, tenant_id, user_id)
        before = len(entries)
        _bucket(store, tenant_id, user_id)[:] = [e for e in entries if e["id"] != memory_id]
        changed = len(_bucket(store, tenant_id, user_id)) < before
        if changed:
            _save_store(store)
        return changed


def long_stats(tenant_id: str, user_id: str) -> dict:
    entries = list_long(tenant_id, user_id)
    return {
        "total": len(entries),
        "authorized": sum(1 for e in entries if e["authorized"]),
        "pending": sum(1 for e in entries if not e["authorized"]),
        "sensitive": sum(1 for e in entries if e["sensitive"]),
    }


def long_prompt_block(tenant_id: str, user_id: str) -> str:
    """组装可注入 Prompt 的长期记忆文本（仅授权且未过期的稳定信息）。
    注意：业务事实（价格/政策等）不入记忆，Prompt 中明确要求以检索结果为准。
    """
    items = effective_long(tenant_id, user_id)
    if not items:
        return ""
    lines = [f"- ({e['category']}) {e['content']}" for e in items]
    return (
        "【用户画像记忆（仅稳定偏好，供参考）】\n" + "\n".join(lines) +
        "\n注意：楼盘价格、库存、政策等业务数据必须以本次知识库检索结果为准，禁止依据记忆回答。"
    )
