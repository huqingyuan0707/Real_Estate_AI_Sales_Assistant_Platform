"""AI 一键装修图接口（技术方案 5.2.1 契约实现）

鉴权：generate/status/history 需登录；/file 与 /download 开放
（浏览器 img/window.open 无法带 Token，文件名 UUID 不可枚举）。
"""
from typing import Literal

import base64
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.rbac import get_current_user
from app.core.responses import ok
from app.services.furniture import valid_ids as valid_furniture_ids
from app.services.render import (
    FLOOR_PROMPTS,
    RENDER_DIR,
    WALL_COLOR_PROMPTS,
    delete_history,
    get_task,
    list_history,
    submit_render,
)

router = APIRouter()

MAX_PHOTO_BYTES = 8 * 1024 * 1024  # 毛坯房照片上限 8MB


class RenderRequest(BaseModel):
    """纯 JSON 提交（无照片文生图模式，保留兼容）"""
    house_task_id: str
    layout_plan: Literal["normal", "hall", "open"] = "normal"
    style: Literal["modern", "chinese", "light", "wood"] = "modern"
    scene: Literal["living_room", "master_bedroom", "dining_room"] = "living_room"
    resolution: Literal["2k", "4k"] = "2k"


@router.post("/generate", dependencies=[Depends(get_current_user)])
async def generate(
    house_task_id: str = Form("local-demo"),
    layout_plan: str = Form("normal"),
    style: str = Form("modern"),
    scene: str = Form("living_room"),
    resolution: str = Form("2k"),
    furniture: str = Form("[]"),
    wall_color: str = Form("cream"),
    floor_style: str = Form("polished_tile"),
    strength: float = Form(0.75),
    photo_width: int = Form(0),
    photo_height: int = Form(0),
    photo: UploadFile | None = File(None),
):
    """提交装修图生成任务（异步，multipart 表单）。

    - 带 photo：图生图——毛坯房照片保持结构，按家具清单/墙色/地面材质重绘装修
    - 不带 photo：纯文生图（原链路）
    """
    photo_b64 = None
    if photo is not None and photo.filename:
        raw = await photo.read()
        if not raw:
            raise HTTPException(status_code=400, detail="照片内容为空")
        if len(raw) > MAX_PHOTO_BYTES:
            raise HTTPException(status_code=413, detail="照片不能超过 8MB")
        if not photo.content_type or not photo.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="仅支持图片格式（jpg/png/webp）")
        photo_b64 = base64.b64encode(raw).decode()

    try:
        furniture_list = json.loads(furniture)
    except Exception:
        furniture_list = []
    if not isinstance(furniture_list, list):
        furniture_list = []

    task = await submit_render(
        house_task_id, layout_plan, style, scene, resolution,
        photo_b64=photo_b64,
        photo_size=(photo_width or 1280, photo_height or 960),
        furniture=valid_furniture_ids(furniture_list),
        wall_color=wall_color if wall_color in WALL_COLOR_PROMPTS else "cream",
        floor_style=floor_style if floor_style in FLOOR_PROMPTS else "polished_tile",
        strength=strength,
    )
    return ok({
        "task_id": task.task_id,
        "status": task.status,
        "mode": task.mode,
        "estimated_seconds": 15 if task.mode == "cloud" else (180 if task.mode == "comfyui" else 8),
    })


@router.get("/history", dependencies=[Depends(get_current_user)])
async def history(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    style: str | None = Query(None, description="按风格过滤：modern/chinese/light/wood"),
    mode: str | None = Query(None, description="按模式过滤：cloud/comfyui/simulate"),
):
    """AI 生图历史记录（持久化，重启不丢；新→旧倒序分页）"""
    return ok(list_history(page=page, page_size=page_size, style=style, mode=mode))


@router.delete("/history/{task_id}", dependencies=[Depends(get_current_user)])
async def remove_history(task_id: str):
    """删除一条生成历史记录及本地成图文件"""
    if not delete_history(task_id):
        raise HTTPException(status_code=404, detail="history record not found")
    return ok({"task_id": task_id}, "历史记录已删除")


@router.get("/{task_id}", dependencies=[Depends(get_current_user)])
async def status(task_id: str):
    """查询渲染进度与结果（前端轮询或走 SSE /task/{task_id}/stream）"""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return ok(task.snapshot())


@router.get("/{task_id}/file")
async def file(task_id: str):
    """本地落地成图（云端生图成功后自动保存，链接永不过期）"""
    path = RENDER_DIR / f"{task_id}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="image file not found")
    return FileResponse(path, media_type="image/png", filename=f"render_{task_id}.png")


@router.get("/{task_id}/download")
async def download(task_id: str):
    """下载成图：本地有文件直接回文件，否则云端/ComfyUI 模式 302 跳转原始 URL"""
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    local = RENDER_DIR / f"{task_id}.png"
    if local.exists():
        return FileResponse(local, media_type="image/png", filename=f"render_{task_id}.png")
    if task.image_url and task.mode in ("cloud", "comfyui"):
        from fastapi.responses import RedirectResponse
        return RedirectResponse(task.image_url)
    return ok({"message": "演示模式无实体文件，配置生图 API Key 或启动 ComfyUI 后可下载成图"})
