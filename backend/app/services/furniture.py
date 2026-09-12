"""业主家具清单服务：清单库持久化 + AI 解析业主上传清单 + 成图落地校验

- 清单库 data/furniture_catalog.json 持久化（RLock 线程安全，原子写）：
  内置 5 分类 / 32 项（与前端 HouseEditorView FURNITURE_GROUPS 及渲染英文提示词一致）。
  首启播种；旧文件升级自动补齐缺失内置项（removed_builtin 内的不补回），自定义项不丢
- render.py 英文提示词唯一数据源 prompt_map()：id → (中文名, en)；en 缺省回退中文名
- parse_furniture_list(text, photo_b64)：业主粘贴文本 / 手写清单照片 → AI 结构化提取并
  标记清单库命中（名称 / 别名 / 包含匹配）；AI 不可用降级分隔符切词
- verify_render(image_b64, furniture_cn)：成图后 VLM 逐项校验 present / missing
"""
import json
import re
import threading
import uuid
from pathlib import Path

import httpx

from app.config import settings
from app.services.ai_config import effective_render
from app.services.space_ai import _extract_json, _is_cloud_chat_available

_CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "furniture_catalog.json"
CATALOG_VERSION = 1
_LOCK = threading.RLock()

# 内置分类（顺序即前端展示顺序）
_BUILTIN_CATEGORIES = [
    {"id": "living", "name": "客餐厅", "builtin": True},
    {"id": "bedroom", "name": "卧室", "builtin": True},
    {"id": "study", "name": "书房", "builtin": True},
    {"id": "appliance", "name": "家电", "builtin": True},
    {"id": "soft", "name": "软装", "builtin": True},
]

# 内置 32 项：(id, 中文名, 英文渲染提示词, 分类id) —— 与前端家具分组一致
_BUILTIN_ITEMS = [
    ("corner_sofa", "转角沙发", "an L-shaped fabric corner sofa", "living"),
    ("sofa", "沙发", "a comfortable fabric sofa", "living"),
    ("coffee_table", "茶几", "a wooden coffee table", "living"),
    ("dining_table", "餐桌", "a dining table with chairs", "living"),
    ("dining_chair", "餐椅", "dining chairs around the table", "living"),
    ("tv", "电视机", "a flat-screen TV on a media console", "living"),
    ("tv_cabinet", "电视柜", "a low TV cabinet", "living"),
    ("sideboard", "餐边柜", "a sideboard cabinet against the wall", "living"),
    ("wine_cabinet", "酒柜", "a glass-door wine cabinet", "living"),
    ("bed", "大床", "a queen size bed with clean bedding", "bedroom"),
    ("bedside_table", "床头柜", "a bedside table next to the bed", "bedroom"),
    ("wardrobe", "衣柜", "a built-in wardrobe", "bedroom"),
    ("dresser", "五斗柜", "a wooden chest of drawers", "bedroom"),
    ("vanity", "梳妆台", "a vanity dressing table with mirror", "bedroom"),
    ("baby_crib", "婴儿床", "a cozy baby crib", "bedroom"),
    ("bookshelf", "书架", "a bookshelf with books", "study"),
    ("desk", "书桌", "a study desk", "study"),
    ("office_chair", "人体工学椅", "an ergonomic office chair", "study"),
    ("fridge", "冰箱", "a refrigerator", "appliance"),
    ("ac", "空调", "an air conditioner", "appliance"),
    ("washer", "洗衣机", "a washing machine", "appliance"),
    ("water_heater", "热水器", "a wall-mounted water heater", "appliance"),
    ("microwave", "微波炉", "a microwave oven on the counter", "appliance"),
    ("oven", "烤箱", "a built-in oven", "appliance"),
    ("dishwasher", "洗碗机", "a dishwasher under the kitchen counter", "appliance"),
    ("carpet", "地毯", "a soft area rug on the floor", "soft"),
    ("curtain", "窗帘", "floor-to-ceiling fabric curtains", "soft"),
    ("potted_plant", "盆栽", "green potted plants", "soft"),
    ("floor_lamp", "落地灯", "a modern floor lamp", "soft"),
    ("wall_art", "装饰挂画", "framed wall art paintings", "soft"),
    ("full_mirror", "全身镜", "a full-length leaning mirror", "soft"),
    ("treadmill", "跑步机", "a treadmill", "soft"),
]


def _default_catalog() -> dict:
    return {
        "version": CATALOG_VERSION,
        "removed_builtin": [],
        "categories": [dict(c) for c in _BUILTIN_CATEGORIES],
        "items": [
            {"id": i, "name": n, "en": e, "category": c, "aliases": [], "builtin": True}
            for i, n, e, c in _BUILTIN_ITEMS
        ],
    }


def _save(data: dict) -> None:
    """原子写清单库：先写临时文件再替换，避免写一半损坏"""
    _CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _CATALOG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_CATALOG_PATH)


def _normalize_item(it: dict) -> dict:
    return {
        "id": it["id"], "name": it["name"], "en": it.get("en") or "",
        "category": it.get("category", "soft"), "aliases": list(it.get("aliases") or []),
        "builtin": bool(it.get("builtin", False)),
    }


def _ensure() -> dict:
    """加载 / 播种 / 升级清单库。必须在 _LOCK 内调用。"""
    data = None
    if _CATALOG_PATH.exists():
        try:
            data = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = None
    if not isinstance(data, dict):
        data = _default_catalog()
    else:
        removed = set(data.setdefault("removed_builtin", []) or [])
        cats = data.setdefault("categories", [])
        have_cat = {c.get("id") for c in cats if isinstance(c, dict)}
        for c in _BUILTIN_CATEGORIES:
            if c["id"] not in have_cat:
                cats.append(dict(c))
        items = data.setdefault("items", [])
        have_item = {i.get("id") for i in items if isinstance(i, dict)}
        for i, n, e, c in _BUILTIN_ITEMS:
            if i not in have_item and i not in removed:
                items.append({"id": i, "name": n, "en": e, "category": c, "aliases": [], "builtin": True})
        data["items"] = [_normalize_item(it) for it in items if isinstance(it, dict)]
        data["version"] = CATALOG_VERSION
    _save(data)
    return data


# ---------------- 查询（渲染层唯一数据源） ----------------

def get_catalog() -> dict:
    """清单库全量：{categories: [{id,name,builtin}], items: [家具条目]}"""
    with _LOCK:
        data = _ensure()
        return {"categories": data["categories"], "items": data["items"]}


def item_list() -> list[dict]:
    with _LOCK:
        return list(_ensure()["items"])


def prompt_map() -> dict[str, tuple[str, str]]:
    """render 兼容：item_id → (中文名, 英文提示词)；en 缺省回退中文名"""
    return {it["id"]: (it["name"], it["en"] or it["name"]) for it in item_list()}


def valid_ids(ids) -> list[str]:
    """过滤清单库中真实存在的 id（去重保序），供渲染提交参数校验"""
    if not ids:
        return []
    known = {it["id"] for it in item_list()}
    out = []
    for i in ids:
        if isinstance(i, str) and i in known and i not in out:
            out.append(i)
    return out


def name_of(item_id: str) -> str:
    for it in item_list():
        if it["id"] == item_id:
            return it["name"]
    return ""


def names(item_ids) -> list[str]:
    """按给定顺序转中文名（未知 id 跳过）"""
    return [n for n in (name_of(i) for i in (item_ids or [])) if n]


def en_of(item_id: str) -> str:
    """英文渲染提示词；en 缺省回退中文名（Kolors 可理解中文）"""
    return {it["id"]: (it["en"] or it["name"]) for it in item_list()}.get(item_id, "")


# ---------------- 分类 / 条目 CRUD ----------------

def _find_cat(cats: list[dict], cat_id: str) -> dict:
    for c in cats:
        if c["id"] == cat_id:
            return c
    raise ValueError(f"分类不存在: {cat_id}")


def _name_taken(items: list[dict], name: str, ignore_id: str | None = None) -> bool:
    return any(it["id"] != ignore_id and it["name"] == name for it in items)


def _clean_aliases(aliases) -> list[str]:
    out = []
    for a in aliases or []:
        a = (a or "").strip()
        if a and a not in out:
            out.append(a)
    return out


def add_category(name: str) -> dict:
    """新增自定义分类（内置分类由文件播种）"""
    name = (name or "").strip()
    if not name:
        raise ValueError("分类名称不能为空")
    with _LOCK:
        data = _ensure()
        if any(c["name"] == name for c in data["categories"]):
            raise ValueError(f"分类已存在: {name}")
        cat = {"id": f"c_{uuid.uuid4().hex[:8]}", "name": name, "builtin": False}
        data["categories"].append(cat)
        _save(data)
        return dict(cat)


def delete_category(cat_id: str) -> None:
    """删除自定义分类；内置分类或分类下仍有家具时禁删"""
    with _LOCK:
        data = _ensure()
        cat = _find_cat(data["categories"], cat_id)
        if cat.get("builtin"):
            raise ValueError("内置分类不可删除")
        if any(it["category"] == cat_id for it in data["items"]):
            raise ValueError(f"分类「{cat['name']}」下还有家具，请先移走或删除")
        data["categories"] = [c for c in data["categories"] if c["id"] != cat_id]
        _save(data)


def add_item(name: str, category: str, en: str = "", aliases=None) -> dict:
    """新增家具条目；name 重复报错，en / aliases 可空"""
    name = (name or "").strip()
    if not name:
        raise ValueError("家具名称不能为空")
    with _LOCK:
        data = _ensure()
        _find_cat(data["categories"], category)
        if _name_taken(data["items"], name):
            raise ValueError(f"家具已存在: {name}")
        it = {"id": f"f_{uuid.uuid4().hex[:8]}", "name": name, "en": (en or "").strip(),
              "category": category, "aliases": _clean_aliases(aliases), "builtin": False}
        data["items"].append(it)
        _save(data)
        return dict(it)


def update_item(item_id: str, name: str | None = None, en: str | None = None,
                aliases: list | None = None, category: str | None = None) -> dict:
    """编辑条目（名称 / 英文提示词 / 别名 / 分类）；名称冲突报错"""
    with _LOCK:
        data = _ensure()
        items = data["items"]
        it = next((x for x in items if x["id"] == item_id), None)
        if not it:
            raise ValueError(f"家具不存在: {item_id}")
        if name is not None:
            name = name.strip()
            if not name:
                raise ValueError("家具名称不能为空")
            if _name_taken(items, name, ignore_id=item_id):
                raise ValueError(f"家具已存在: {name}")
            it["name"] = name
        if en is not None:
            it["en"] = en.strip()
        if aliases is not None:
            it["aliases"] = _clean_aliases(aliases)
        if category is not None:
            _find_cat(data["categories"], category)
            it["category"] = category
        data["items"] = [_normalize_item(x) for x in items]
        _save(data)
        return dict(_normalize_item(it))


def delete_item(item_id: str) -> bool:
    """删除条目：自定义直接删；内置记入 removed_builtin，防文件升级时复活"""
    with _LOCK:
        data = _ensure()
        it = next((x for x in data["items"] if x["id"] == item_id), None)
        if not it:
            return False
        data["items"] = [x for x in data["items"] if x["id"] != item_id]
        if it.get("builtin"):
            data.setdefault("removed_builtin", []).append(item_id)
        _save(data)
        return True


# ---------------- AI 解析业主家具清单 ----------------

_PARSE_PROMPT = (
    "你是房产销售的业主家具清单整理助手。业主提供了一份装修家具/家电清单（粘贴文本或清单照片），"
    "请逐项整理为通用中文名（如“转角沙发”“洗衣机”“儿童学习桌”），同义项合并不要重复，"
    "只输出 JSON（不要多余文字）：\n"
    '{"items":[{"name":"家具/家电通用中文名","count":"数量数字或空字符串"}]}\n'
    "常规家具家电之外的装饰软装（窗帘/绿植/挂画等）也一并列出；清单为空返回 {\"items\":[]}。"
)


def _split_list(text: str) -> list[tuple[str, str]]:
    """降级切词：按常见分隔符拆分，去“1、”序号与尾缀数量，返回 [(名称, 数量)]"""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for part in re.split(r"[\n\r,，、;；/。]+", text or ""):
        name = part.strip().strip("（）()[]【】")
        if not name:
            continue
        name = re.sub(r"^[一二三四五六七八九十]?[\s\d]*[.、．:：]\s*", "", name)
        if not name or name.replace(" ", "").isdigit():
            continue
        count = ""
        m = re.match(r"^(?P<nm>.+?)\s*[xX×*]\s*(?P<c>\d+)$", name)
        if m:
            name, count = m.group("nm").strip(), m.group("c")
        else:
            m = re.match(r"^(?P<nm>.+?)\s*(?P<c>\d+)\s*(?:个|台|张|把|件|组|套)?$", name)
            if m:
                name, count = m.group("nm").strip(), m.group("c")
        if not name or name in seen:
            continue
        seen.add(name)
        out.append((name, count))
    return out


def _match_catalog_id(items: list[dict], name: str) -> str | None:
    """清单库命中：精确名/别名 → 双向包含匹配（均去空白）"""
    key = re.sub(r"\s+", "", name)
    if not key:
        return None
    for it in items:
        if key == re.sub(r"\s+", "", it["name"]):
            return it["id"]
        if any(key == re.sub(r"\s+", "", a) for a in it["aliases"]):
            return it["id"]
    for it in items:
        nm = re.sub(r"\s+", "", it["name"])
        if len(nm) >= 2 and (nm in key or key in nm):
            return it["id"]
    return None


def _build_items(raw_items: list | None, catalog_items: list[dict]) -> list[dict]:
    """把 AI / 切词结果统一映射为条目，并标注清单库命中情况"""
    out: list[dict] = []
    seen: set[str] = set()
    for raw in raw_items or []:
        name = (raw.get("name") if isinstance(raw, dict) else raw) if raw else None
        name = re.sub(r"\s+", "", str(name or "")).strip()
        if not name or name.isdigit() or name in seen:
            continue
        seen.add(name)
        count = ""
        if isinstance(raw, dict):
            c = raw.get("count")
            if isinstance(c, (int, float)):
                count = str(c)
            elif isinstance(c, str) and c.strip():
                count = c.strip()
        mid = _match_catalog_id(catalog_items, name)
        out.append({"name": name, "count": count, "catalog_id": mid, "in_catalog": mid is not None})
    return out


async def parse_furniture_list(text: str = "", photo_b64: str = "") -> dict:
    """解析业主家具清单：粘贴文本走 LLM、清单照片走 VLM；AI 不可用降级切词。
    返回 {"source": "ai"|"rules", "ocr": bool, "note": str, "items":[{name,count,catalog_id,in_catalog}]}"""
    text = (text or "").strip()
    photo_ok = bool(photo_b64)
    if not text and not photo_ok:
        return {"source": "rules", "ocr": False, "note": "清单为空", "items": []}
    catalog_items = item_list()
    if settings.SPACE_AI_ENABLED and _is_cloud_chat_available():
        try:
            if photo_ok:
                content = [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{photo_b64}"}},
                    {"type": "text", "text": _PARSE_PROMPT + (f"\n业主另粘贴了文本可互为补充：{text}" if text else "")},
                ]
                model = settings.SPACE_VLM_MODEL
            else:
                content = _PARSE_PROMPT + f"\n清单内容：{text}"
                model = settings.SPACE_LLM_MODEL
            cfg = effective_render()
            async with httpx.AsyncClient(timeout=settings.SPACE_AI_TIMEOUT, trust_env=False) as c:
                r = await c.post(
                    f"{cfg['base_url'].rstrip('/')}/chat/completions",
                    headers={"Authorization": f"Bearer {cfg['api_key']}"},
                    json={"model": model, "messages": [{"role": "user", "content": content}],
                          "temperature": 0.2, "max_tokens": 900},
                )
                r.raise_for_status()
                data = _extract_json(r.json()["choices"][0]["message"]["content"].strip())
            if not isinstance(data, dict) or not isinstance(data.get("items"), list):
                raise ValueError("bad parse json")
            return {"source": "ai", "ocr": photo_ok, "note": "", "items": _build_items(data["items"], catalog_items)}
        except Exception as e:
            print(f"[furniture] AI 解析清单降级（切词兜底）: {type(e).__name__}: {e}")
    # 降级：文本分隔符切词；仅照片且无 AI 时无法读图，如实说明
    if photo_ok and not text:
        return {"source": "rules", "ocr": True, "note": "照片识别需云端 AI（当前未配置或不可用），请直接粘贴清单文字", "items": []}
    return {"source": "rules", "ocr": False, "note": "AI 不可用，已按文本切词", "items": _build_items(
        [{"name": n, "count": c} for n, c in _split_list(text)], catalog_items)}


# ---------------- 成图落地校验（渲染完成后 VLM 逐项核对） ----------------

_VERIFY_PROMPT = (
    "你是室内效果图验收质检员。请检查这张 AI 生成的室内效果图，逐项判断下列家具/物品是否真实出现在图中"
    "（近似同款算出现，背景模糊但可辨认也算；没有的东西严禁脑补为出现）。\n"
    "物品清单：{items}\n"
    '只输出 JSON（不要多余文字）：{"results":[{"name":"清单原词","present":true或false,'
    '"note":"一句话依据，如 沙发左侧有转角沙发"}]}'
)


async def verify_render(image_b64: str, furniture_cn: list[str]) -> dict:
    """VLM 逐项校验成图中家具是否落地。不可用（未配云 AI / 无可校验项）返回 available=False。"""
    names_cn = [n for n in (furniture_cn or []) if n.strip()]
    if not names_cn or not image_b64 or not (settings.SPACE_AI_ENABLED and _is_cloud_chat_available()):
        return {"available": False, "items": names_cn, "present": 0, "total": len(names_cn),
                "reason": "AI 视觉校验不可用（未配置云 Key 或无校验项）"}
    try:
        cfg = effective_render()
        async with httpx.AsyncClient(timeout=settings.SPACE_AI_TIMEOUT, trust_env=False) as c:
            r = await c.post(
                f"{cfg['base_url'].rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {cfg['api_key']}"},
                json={
                    "model": settings.SPACE_VLM_MODEL,
                    "messages": [{"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                        {"type": "text", "text": _VERIFY_PROMPT.format(items="、".join(names_cn))},
                    ]}],
                    "temperature": 0.0,
                    "max_tokens": 800,
                },
            )
            r.raise_for_status()
            data = _extract_json(r.json()["choices"][0]["message"]["content"].strip())
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise ValueError("bad verify json")
        results = data["results"][:len(names_cn)]
        present = sum(1 for x in results if x.get("present") is True)
        return {"available": True, "items": names_cn, "results": results,
                "present": present, "total": len(names_cn), "reason": ""}
    except Exception as e:
        print(f"[furniture] 成图校验失败: {type(e).__name__}: {e}")
        return {"available": False, "items": names_cn, "present": 0, "total": len(names_cn),
                "reason": f"校验调用失败: {str(e)[:100]}"}
