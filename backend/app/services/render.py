"""一键装修图渲染服务层（技术方案 5.2.1）

三模式（自动降级链，RENDER_PROVIDER=auto 时按序检测）：
- cloud：配置了 RENDER_API_KEY 时优先走云端生图 API
  （SiliconFlow images/generations 同步返图 / DashScope 通义万相 异步任务轮询）
  支持图生图：上传毛坯房照片（base64）+ 家具清单 + 墙色 + 地面材质 →
  Kolors img2img（strength 控制结构保持度），房间结构/窗户位置/视角保持不变
- comfyui：本机 ComfyUI 可达时，提交 ControlNet-MLSD + SDXL + 风格LoRA 工作流，
  轮询 /history 取图；workflow 支持外置 JSON（COMFYUI_WORKFLOW）
- 演示模式（兜底）：以上均不可用时模拟渲染进度，返回风格色板供前端渲染占位图

任务状态保存在内存（单进程演示足够；生产迁移 render_tasks 表 + Celery）。
"""
import asyncio
import base64
import json
import threading
import time
import uuid
from pathlib import Path

import httpx

from app.config import settings
from app.services import furniture as furniture_svc
from app.services.ai_config import effective_render
from app.services.space_ai import LAYOUT_PHASE, SPACE_PHASE, _fallback_layout, _fallback_space, analyze_space, plan_layout

# 成图本地落地目录（云端/ComfyUI 返回的临时链接有过期时间，持久化到本地）
RENDER_DIR = Path(__file__).resolve().parents[2] / "data" / "renders"
RENDER_DIR.mkdir(parents=True, exist_ok=True)
HISTORY_PATH = RENDER_DIR.parent / "render_history.json"

# 风格 → 色板（演示模式前端渐变用）+ 英文提示词（ComfyUI/真实模式用）
STYLE_CONFIG = {
    "modern": {"name": "现代简约", "palette": ["#dfe7ee", "#c3d0dc", "#eef2f6"],
               "prompt": "modern minimalist interior, clean lines, neutral tones, photorealistic"},
    "chinese": {"name": "新中式", "palette": ["#efe3d3", "#d4b896", "#f4ece0"],
                "prompt": "new chinese style interior, warm wood texture, elegant oriental design, photorealistic"},
    "light": {"name": "轻奢风", "palette": ["#e8e4dc", "#cbb68f", "#f2eee6"],
              "prompt": "light luxury interior, metallic accents, marble texture, soft glam lighting, photorealistic"},
    "wood": {"name": "原木风", "palette": ["#f0e8da", "#d9c4a3", "#f6f1e8"],
             "prompt": "japandi wood style interior, natural oak furniture, warm sunlight, photorealistic"},
}
SCENE_NAMES = {"living_room": "客厅", "master_bedroom": "主卧", "dining_room": "餐厅"}
PHASES = ["正在理解空间结构...", "正在布置灯光与材质...", "正在渲染高清效果图..."]

# 家具条目 id → (中文名, 英文提示词) 的唯一数据源在 furniture.py（prompt_map），
# 由清单库文件 data/furniture_catalog.json 持久化，支持业主自定义家具增删。
WALL_COLOR_PROMPTS = {
    "white": ("奶白色", "warm white painted walls"),
    "cream": ("奶油色", "cream colored walls"),
    "beige": ("大地米色", "beige walls with wood trim"),
    "gray": ("高级灰", "modern gray painted walls"),
    "green": ("复古绿", "a retro green accent wall"),
    "blue": ("雾霾蓝", "haze blue painted walls"),
    "terracotta": ("陶土橙", "a terracotta orange accent wall"),
}
FLOOR_PROMPTS = {
    "polished_tile": ("抛光瓷砖", "polished ceramic floor tiles"),
    "marble_tile": ("大理石纹瓷砖", "marble patterned porcelain floor tiles"),
    "oak_floor": ("橡木地板", "light oak wood flooring"),
    "walnut_floor": ("胡桃木地板", "dark walnut wood flooring"),
    "cement_tile": ("水泥灰砖", "cement gray floor tiles"),
}
# 图生图只认支持 img2img 的模型（Qwen-Image 是纯文生图）
IMG2IMG_MODEL = "Kwai-Kolors/Kolors"


class RenderTask:
    def __init__(
        self,
        house_task_id: str,
        layout_plan: str,
        style: str,
        scene: str,
        resolution: str,
        photo_b64: str | None = None,
        photo_size: tuple[int, int] = (1280, 960),
        furniture: list[str] | None = None,
        wall_color: str = "cream",
        floor_style: str = "polished_tile",
        strength: float = 0.75,
    ):
        self.task_id = uuid.uuid4().hex
        self.house_task_id = house_task_id
        self.layout_plan = layout_plan
        self.style = style
        self.scene = scene
        self.resolution = resolution
        # 图生图：毛坯房照片（base64，无则纯文生图）+ 业主定制参数
        self.photo_b64 = photo_b64
        self.photo_size = photo_size
        self.furniture = furniture_svc.valid_ids(furniture or [])
        self.wall_color = wall_color if wall_color in WALL_COLOR_PROMPTS else "cream"
        self.floor_style = floor_style if floor_style in FLOOR_PROMPTS else "polished_tile"
        self.strength = min(0.9, max(0.4, strength))
        self.status = "queued"  # queued/running/done/failed
        self.progress = 0
        self.phase = ""
        self.mode = "simulate"  # cloud / comfyui / simulate
        self.image_url = None
        self.created_at = time.time()
        # 三步流水线中间产物（看懂空间 / 构思布局），前端展示 AI 思考过程
        self.space_result: dict | None = None
        self.layout_result: dict | None = None
        # 成图落地后 VLM 校验结果（家具逐项 present/missing，未校验为 None）
        self.verify_result: dict | None = None

    def snapshot(self) -> dict:
        cfg = STYLE_CONFIG.get(self.style, STYLE_CONFIG["modern"])
        return {
            "task_id": self.task_id,
            "status": self.status,
            "progress": self.progress,
            "phase": self.phase,
            "mode": self.mode,
            "style_name": cfg["name"],
            "scene_name": SCENE_NAMES.get(self.scene, self.scene),
            "palette": cfg["palette"],
            "image_url": self.image_url,
            # 图生图参数回显
            "has_photo": bool(self.photo_b64),
            "furniture_names": furniture_svc.names(self.furniture),
            "wall_color_name": WALL_COLOR_PROMPTS[self.wall_color][0],
            "floor_name": FLOOR_PROMPTS[self.floor_style][0],
            "strength": self.strength,
            # 三步流水线：空间理解与布局方案（未开始为 None）
            "space_result": self.space_result,
            "layout_result": self.layout_result,
            "verify_result": self.verify_result,
        }


_tasks: dict[str, RenderTask] = {}

# ---------------- 生成历史（data/render_history.json 持久化，重启不丢） ----------------
_HISTORY_LIMIT = 500  # 最多保留最近 500 条
_HIST_LOCK = threading.Lock()


def _append_history(task: RenderTask, duration_s: float) -> None:
    """任务结束（done/failed）时落一条历史记录"""
    cfg = STYLE_CONFIG.get(task.style, STYLE_CONFIG["modern"])
    record = {
        "task_id": task.task_id,
        "house_task_id": task.house_task_id,
        "layout_plan": task.layout_plan,
        "style": task.style,
        "style_name": cfg["name"],
        "scene": task.scene,
        "scene_name": SCENE_NAMES.get(task.scene, task.scene),
        "resolution": task.resolution,
        "mode": task.mode,
        "status": task.status,
        "image_url": task.image_url,
        # 图生图参数快照（前端历史卡片回显）
        "has_photo": bool(task.photo_b64),
        "furniture_names": furniture_svc.names(task.furniture),
        "wall_color_name": WALL_COLOR_PROMPTS[task.wall_color][0],
        "floor_name": FLOOR_PROMPTS[task.floor_style][0],
        "strength": task.strength,
        "local_file": (RENDER_DIR / f"{task.task_id}.png").exists(),
        "duration_s": round(duration_s, 1),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(task.created_at)),
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with _HIST_LOCK:
        try:
            history = json.loads(HISTORY_PATH.read_text(encoding="utf-8")) if HISTORY_PATH.exists() else []
        except Exception:
            history = []
        history.insert(0, record)  # 新记录在前
        HISTORY_PATH.write_text(json.dumps(history[:_HISTORY_LIMIT], ensure_ascii=False, indent=2), encoding="utf-8")


def list_history(page: int = 1, page_size: int = 10, style: str | None = None, mode: str | None = None) -> dict:
    """分页查询生成历史（新→旧），支持按风格/模式过滤"""
    with _HIST_LOCK:
        try:
            history = json.loads(HISTORY_PATH.read_text(encoding="utf-8")) if HISTORY_PATH.exists() else []
        except Exception:
            history = []
    if style:
        history = [h for h in history if h.get("style") == style]
    if mode:
        history = [h for h in history if h.get("mode") == mode]
    total = len(history)
    start = (page - 1) * page_size
    return {"total": total, "page": page, "page_size": page_size, "items": history[start:start + page_size]}


def delete_history(task_id: str) -> bool:
    """删除一条历史记录及其本地成图文件"""
    with _HIST_LOCK:
        try:
            history = json.loads(HISTORY_PATH.read_text(encoding="utf-8")) if HISTORY_PATH.exists() else []
        except Exception:
            history = []
        rest = [h for h in history if h.get("task_id") != task_id]
        if len(rest) == len(history):
            return False
        HISTORY_PATH.write_text(json.dumps(rest, ensure_ascii=False, indent=2), encoding="utf-8")
    (RENDER_DIR / f"{task_id}.png").unlink(missing_ok=True)
    return True


def get_task(task_id: str) -> RenderTask | None:
    return _tasks.get(task_id)


def get_all_tasks() -> list[RenderTask]:
    """全部渲染任务（任务中心列表合并用）"""
    return list(_tasks.values())


def cancel_task(task_id: str) -> bool:
    """取消渲染任务（统一任务中心 DELETE /tasks/{id} 委托入口）"""
    t = _tasks.get(task_id)
    if not t or t.status in ("done", "failed", "cancelled"):
        return False
    t.status = "cancelled"
    t.phase = "已取消"
    return True


# ---------------- 云端生图 API（SiliconFlow / DashScope 通义万相） ----------------

LAYOUT_NAMES = {"normal": "常规布局", "hall": "横厅布局", "open": "开放式布局"}


def _cloud_prompt(task: RenderTask) -> str:
    cfg = STYLE_CONFIG.get(task.style, STYLE_CONFIG["modern"])
    scene_cn = SCENE_NAMES.get(task.scene, task.scene)
    if task.photo_b64:
        # 图生图：强调保持房间结构/门窗/视角不变，只做装修与家具布置
        furn = [furniture_svc.en_of(f) for f in task.furniture]
        furn_txt = f"place {', '.join(furn)}" if furn else "keep it tidy and uncluttered"
        wall = WALL_COLOR_PROMPTS[task.wall_color][1]
        floor = FLOOR_PROMPTS[task.floor_style][1]
        # 三步流水线增量：空间理解的结构特征 + 布局方案的摆放描述（降级时为空串，不破坏主链路）
        space_hints = (task.space_result or {}).get("render_hints", "")
        layout_hints = (task.layout_result or {}).get("enriched_prompt", "")
        extra = ", ".join(x.strip() for x in (space_hints, layout_hints) if x and x.strip())
        core = (
            f"Renovate this real empty room photo into a finished {scene_cn} ({task.scene}) interior, "
            f"keep the room structure, window and door positions, ceiling height and camera angle exactly unchanged, "
            f"{cfg['prompt']}, {wall}, {floor}, {furn_txt}, "
        )
        tail = "realistic interior photography, soft natural lighting, high quality, ultra detailed, no watermark"
        return f"{core}{extra}, {tail}" if extra else f"{core}{tail}"
    # 纯文生图（无毛坯照片）
    plan_cn = LAYOUT_NAMES.get(task.layout_plan, task.layout_plan)
    return (
        f"Real estate interior design photo, {cfg['prompt']}, {scene_cn} ({task.scene}), "
        f"{plan_cn}, fully furnished, soft natural lighting, wide-angle real shot, "
        f"high quality, ultra detailed, no watermark"
    )


async def _cloud_tickle(task: RenderTask) -> None:
    """云端同步 API 期间无法感知真实进度，做软进度推进"""
    for _ in range(120):
        if task.status != "running":
            return
        task.progress = min(task.progress + 3, 92)
        task.phase = "云端 AI 渲染中..."
        await asyncio.sleep(1)


async def _cloud_run(task: RenderTask) -> None:
    task.status = "running"
    # 三步流水线（图生图模式）：①看懂空间 → ②构思布局 → ③渲染效果
    # 前两步失败各自降级不抛错，始终能落到第三步渲染
    furn_cn = furniture_svc.names(task.furniture)
    if task.photo_b64:
        task.progress = 4
        task.phase = SPACE_PHASE
        task.space_result = await analyze_space(task.photo_b64, task.scene)
        task.progress = 16
        task.phase = LAYOUT_PHASE
        task.layout_result = await plan_layout(task.space_result, furn_cn, task.style, task.scene)
        task.progress = 30
    task.phase = "正在调用云端 AI 生成..."
    prompt = _cloud_prompt(task)
    # 地址/Key/模型：当前用户在前端保存的配置优先，未配置项回退全局 .env
    cfg = effective_render()
    base = cfg["base_url"].rstrip("/")
    is_dashscope = cfg["provider"].lower() == "dashscope" or "dashscope" in base or "aliyuncs" in base
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}
    if task.photo_b64:
        # 图生图：按原图比例计算输出尺寸（最长边 1280，8 对齐；Kolors 支持 512~2048 自由尺寸）
        w, h = task.photo_size
        k = 1280.0 / max(w, h)
        size = f"{max(512, int(w * k) // 8 * 8)}x{max(512, int(h * k) // 8 * 8)}"
    else:
        size = "2048x2048" if task.resolution == "4k" else "1024x1024"
    image_url: str | None = None

    tickle = asyncio.create_task(_cloud_tickle(task))
    try:
        async with httpx.AsyncClient(timeout=settings.RENDER_API_TIMEOUT, trust_env=False) as c:
            if is_dashscope:
                # 通义万相：提交异步任务 → 轮询取图
                r = await c.post(
                    "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis",
                    headers={**headers, "X-DashScope-Async": "enable"},
                    json={
                        "model": cfg["model"],
                        "input": {"prompt": prompt},
                        "parameters": {"size": size.replace("x", "*"), "n": 1},
                    },
                )
                r.raise_for_status()
                dash_task_id = r.json()["output"]["task_id"]
                while True:
                    await asyncio.sleep(2)
                    h = await c.get(
                        f"https://dashscope.aliyuncs.com/api/v1/tasks/{dash_task_id}", headers=headers,
                    )
                    h.raise_for_status()
                    out = h.json()["output"]
                    if out["task_status"] == "SUCCEEDED":
                        image_url = out["results"][0]["url"]
                        break
                    if out["task_status"] != "PENDING" and out["task_status"] != "RUNNING":
                        raise RuntimeError(f"通义万相生成失败: {out.get('message', out['task_status'])}")
                    task.progress = min(int(task.progress) + 6, 92)
                    task.phase = "云端 AI 渲染中..."
            else:
                # 硅基流动：同步接口直接返图 URL；带毛坯照片时走 img2img
                model = cfg["model"]
                payload = {
                    "prompt": prompt,
                    "image_size": size,
                    "batch_size": 1,
                    "num_inference_steps": settings.RENDER_API_STEPS,
                    "guidance_scale": settings.RENDER_API_GUIDANCE,
                }
                if task.photo_b64:
                    if "kolors" not in model.lower():
                        model = IMG2IMG_MODEL  # Qwen-Image 等纯文生图模型不支持 image 参数
                    payload.update({
                        "model": model,
                        "image": f"data:image/png;base64,{task.photo_b64}",
                        "strength": task.strength,
                    })
                else:
                    payload["model"] = model
                r = await c.post(f"{base}/images/generations", headers=headers, json=payload)
                r.raise_for_status()
                data = r.json()
                if data.get("images"):
                    image_url = data["images"][0]["url"]
                elif data.get("data"):
                    image_url = data["data"][0]["url"]
                else:
                    raise RuntimeError(f"云端未返回图片: {str(data)[:200]}")
    finally:
        tickle.cancel()

    if not image_url:
        raise RuntimeError("云端未返回图片 URL")

    # 落地到本地（云端临时链接一般 24h 过期）；失败则回退原始 URL，不影响出图
    local_path = RENDER_DIR / f"{task.task_id}.png"
    try:
        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as c:
            r = await c.get(image_url)
            r.raise_for_status()
            local_path.write_bytes(r.content)
            task.image_url = f"/api/v1/render/{task.task_id}/file"
            task.phase = "渲染完成（云端 AI 生成，已保存本地）"
    except Exception:
        task.image_url = image_url
        task.phase = "渲染完成（云端 AI 生成）"
    # 成图落地后 VLM 逐项校验业主家具是否真实出现在图中（失败/未配置只记不可用，不阻塞出图）
    if local_path.exists() and furn_cn:
        try:
            img_b64 = base64.b64encode(local_path.read_bytes()).decode()
            task.verify_result = await furniture_svc.verify_render(img_b64, furn_cn)
        except Exception as e:
            print(f"[render] 成图校验跳过: {type(e).__name__}: {e}")
            task.verify_result = {"available": False, "reason": f"校验调用失败: {str(e)[:100]}"}
    task.progress = 100
    task.status = "done"


# ---------------- ComfyUI 真实模式 ----------------

async def comfyui_available() -> bool:
    try:
        async with httpx.AsyncClient(timeout=2.0) as c:
            r = await c.get(f"{settings.COMFYUI_BASE_URL}/system_stats")
            return r.status_code == 200
    except Exception:
        return False


def _build_workflow(task: RenderTask, layout_image_b64: str | None) -> dict:
    """构建 ComfyUI API 格式工作流（api 格式 JSON）。
    如配置了 COMFYUI_WORKFLOW 外置模板则从文件加载（生产推荐），
    否则使用最小 txt2img 骨架（接入 ControlNet-MLSD 时在此替换）。"""
    import json

    if settings.COMFYUI_WORKFLOW:
        with open(settings.COMFYUI_WORKFLOW, encoding="utf-8") as f:
            return json.load(f)

    cfg = STYLE_CONFIG.get(task.style, STYLE_CONFIG["modern"])
    steps = 30 if task.resolution == "4k" else 20
    return {
        "3": {"class_type": "KSampler", "inputs": {
            "seed": int(time.time()), "steps": steps, "cfg": 7.0,
            "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 1,
            "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sdxl_base_1.0.safetensors"}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 1024, "height": 1024, "batch_size": 1}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {
            "text": f"{cfg['prompt']}, {SCENE_NAMES.get(task.scene, task.scene)}, "
                    f"layout plan: {task.layout_plan}, high quality, 8k",
            "clip": ["4", 1]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {
            "text": "blurry, low quality, distorted, watermark", "clip": ["4", 1]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
        "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": f"render_{task.task_id}"}},
    }


async def _comfyui_run(task: RenderTask) -> None:
    """提交工作流并轮询直到完成（真实模式）"""
    task.status = "running"
    task.phase = PHASES[0]
    workflow = _build_workflow(task, None)
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.post(f"{settings.COMFYUI_BASE_URL}/prompt", json={"prompt": workflow})
        r.raise_for_status()
        prompt_id = r.json()["prompt_id"]
        while True:
            await asyncio.sleep(1.5)
            h = await c.get(f"{settings.COMFYUI_BASE_URL}/history/{prompt_id}")
            history = h.json().get(prompt_id)
            if not history:
                continue
            if history.get("status", {}).get("completed"):
                outputs = history.get("outputs", {})
                for node in outputs.values():
                    for img in node.get("images", []):
                        task.image_url = f"{settings.COMFYUI_BASE_URL}/view?filename={img['filename']}&subfolder={img.get('subfolder', '')}&type={img.get('type', 'output')}"
                task.progress = 100
                task.phase = "渲染完成"
                task.status = "done"
                return


# ---------------- 演示模式 ----------------

async def _simulate_run(task: RenderTask) -> None:
    """演示模式：按 RENDER_SIM_SECONDS 推进进度，文案对齐三步流水线"""
    task.status = "running"
    # 演示模式同样产出空间理解/布局方案（规则模板），前端展示体验一致
    if task.photo_b64:
        task.space_result = _fallback_space(task.scene)
        task.layout_result = _fallback_layout(furniture_svc.names(task.furniture))
    steps = 24
    for i in range(1, steps + 1):
        await asyncio.sleep(settings.RENDER_SIM_SECONDS / steps)
        if task.status == "cancelled":  # 统一任务中心取消：提前退出渲染循环
            return
        p = int(i / steps * 100)
        task.progress = p
        if task.photo_b64 and p <= 25:
            task.phase = SPACE_PHASE
        elif task.photo_b64 and p <= 45:
            task.phase = LAYOUT_PHASE
        else:
            task.phase = PHASES[min(int(task.progress / 40), 2)]
    task.progress = 100
    task.phase = "渲染完成（演示模式）"
    task.status = "done"


# ---------------- 对外入口 ----------------

async def submit_render(
    house_task_id: str,
    layout_plan: str,
    style: str,
    scene: str,
    resolution: str,
    photo_b64: str | None = None,
    photo_size: tuple[int, int] = (1280, 960),
    furniture: list[str] | None = None,
    wall_color: str = "cream",
    floor_style: str = "polished_tile",
    strength: float = 0.75,
) -> RenderTask:
    """创建任务并后台执行。降级链（auto）：云端 API（配置了 Key）→ ComfyUI → 演示模式
    photo_b64 非空时走图生图（毛坯房照片 + 家具/墙色/地面定制装修）"""
    task = RenderTask(
        house_task_id, layout_plan, style, scene, resolution,
        photo_b64=photo_b64, photo_size=photo_size, furniture=furniture,
        wall_color=wall_color, floor_style=floor_style, strength=strength,
    )
    _tasks[task.task_id] = task

    rcfg = effective_render()
    provider = rcfg["provider"].lower()
    cloud_ok = bool(rcfg["api_key"]) and provider in ("auto", "siliconflow", "dashscope")
    if cloud_ok:
        task.mode = "cloud"
        asyncio.create_task(_safe_run(task, _cloud_run(task)))
    elif provider in ("auto", "comfyui") and await comfyui_available():
        task.mode = "comfyui"
        asyncio.create_task(_safe_run(task, _comfyui_run(task)))
    else:
        task.mode = "simulate"
        asyncio.create_task(_safe_run(task, _simulate_run(task)))
    return task


async def _safe_run(task: RenderTask, coro) -> None:
    start = time.time()
    try:
        await coro
    except Exception as e:
        # 云端失败自动降级演示模式（前端仍可完成流程），ComfyUI 失败置 failed
        if task.mode == "cloud":
            task.phase = f"云端生成失败（{str(e)[:80]}），已自动转演示模式"
            try:
                await _simulate_run(task)
            except Exception as e2:
                task.status = "failed"
                task.phase = f"渲染失败: {e2}"
        else:
            task.status = "failed"
            task.phase = f"渲染失败: {e}"
    finally:
        # done / failed 均记入生成历史（进程重启不丢，供历史记录页查询）
        if task.status in ("done", "failed"):
            try:
                _append_history(task, time.time() - start)
            except Exception:
                pass
