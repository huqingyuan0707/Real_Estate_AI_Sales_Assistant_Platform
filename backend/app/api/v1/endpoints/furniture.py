"""业主家具清单接口：清单库 / 分类与条目 CRUD / 业主上传清单 AI 解析

- catalog：供装修编辑器按分类展示家具 chips（数据源与渲染层一致）
- 分类/条目增删改：内置禁删禁改分类、内置条目删除后不复活，自定义项与库内唯一名
- parse：业主粘贴文本（LLM）或上传清单照片（VLM）→ 结构化清单 + 库内命中标记
- 全部接口需登录（router 统一挂 get_current_user）
"""
import base64

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.core.responses import ok
from app.services import furniture

router = APIRouter()

MAX_PHOTO_BYTES = 8 * 1024 * 1024  # 清单照片上限 8MB
_PARSE_ACCEPT = {"image/jpeg", "image/png", "image/webp"}


class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=20, description="分类名称")


class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=40, description="家具名称（库内唯一）")
    category: str = Field(description="所属分类 id")
    en: str = Field(default="", description="英文渲染提示词（可空，空则回退中文名）")
    aliases: list[str] = Field(default_factory=list, description="业主叫法别名（解析命中用）")


class ItemPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    en: str | None = None
    aliases: list[str] | None = None
    category: str | None = None


@router.get("/catalog")
async def catalog():
    """家具清单库全量（分类 + 条目）"""
    data = furniture.get_catalog()
    return ok({**data, "total": len(data["items"])})


@router.post("/categories")
async def add_category(body: CategoryIn):
    """新增自定义分类"""
    try:
        cat = furniture.add_category(body.name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ok(cat, "分类已添加")


@router.delete("/categories/{cat_id}")
async def remove_category(cat_id: str):
    """删除自定义分类（内置 / 非空分类禁删）"""
    try:
        furniture.delete_category(cat_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ok({"id": cat_id}, "分类已删除")


@router.post("/items")
async def add_item(body: ItemIn):
    """新增家具条目"""
    try:
        it = furniture.add_item(body.name, body.category, en=body.en, aliases=body.aliases)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ok(it, "家具已添加")


@router.put("/items/{item_id}")
async def update_item(item_id: str, body: ItemPatch):
    """编辑家具条目（名称 / 英文提示词 / 别名 / 分类）"""
    patch = body.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(status_code=400, detail="无更新字段")
    try:
        it = furniture.update_item(item_id, **patch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ok(it, "家具已更新")


@router.delete("/items/{item_id}")
async def remove_item(item_id: str):
    """删除家具条目（内置条目删除后不复活，记入 removed_builtin）"""
    if not furniture.delete_item(item_id):
        raise HTTPException(status_code=404, detail="家具不存在")
    return ok({"id": item_id}, "家具已删除")


@router.post("/parse")
async def parse(
    text: str = Form("", description="业主粘贴的清单文字（可空，与照片二选一或并用）"),
    photo: UploadFile | None = File(None, description="业主手写/拍摄的清单照片"),
):
    """AI 解析业主家具清单 → 结构化条目（走 LLM/VLM，降级切词）

    返回 {"source": "ai"|"rules", "ocr": bool, "note": str,
          "items": [{name, count, catalog_id, in_catalog}]}
    """
    photo_b64 = ""
    if photo is not None and photo.filename:
        raw = await photo.read()
        if not raw:
            raise HTTPException(status_code=400, detail="照片内容为空")
        if len(raw) > MAX_PHOTO_BYTES:
            raise HTTPException(status_code=413, detail="清单照片不能超过 8MB")
        if photo.content_type not in _PARSE_ACCEPT:
            raise HTTPException(status_code=400, detail="仅支持图片格式（jpg/png/webp）")
        photo_b64 = base64.b64encode(raw).decode()
    return ok(await furniture.parse_furniture_list(text=text, photo_b64=photo_b64), "清单解析完成")
