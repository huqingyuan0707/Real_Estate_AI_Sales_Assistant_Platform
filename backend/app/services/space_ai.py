"""装修三步流水线 · 前两步 AI 服务（技术方案 5.2.1 扩展）

核心思路（与产品文案一一对应）：
1. 看懂空间 Space Understanding：VLM（多模态）分析毛坯房照片，
   输出结构化 JSON —— 房间类型、墙面/地面/门窗位置、空间结构、采光视角。
2. 构思布局 Layout Planning：LLM 基于【空间理解结果 + 业主家具清单 + 风格偏好】，
   规划家具摆放方案（位置/理由/动线），并产出一段英文渲染提示词增量。
3. 渲染效果 Rendering：由 render.py 调图生图模型完成（本文件不涉及）。

降级策略（每步失败绝不阻塞渲染主链路）：
- VLM 不可用/超时 → 规则模板兜底（依据已选场景与照片尺寸给出保守描述）
- LLM 不可用/超时 → 静态布局模板（家具清单逐项给默认摆位）
仅硅基流动云端（RENDER_API_BASE 含 siliconflow）启用真实 AI 分析，
DashScope/本地模式直接走模板，行为可预期。
"""
import json
import re

import httpx

from app.config import settings
from app.services.ai_config import effective_render

SPACE_PHASE = "正在看懂空间（识别墙面/地面/门窗）..."
LAYOUT_PHASE = "正在构思布局（家具摆放与动线）..."

# ---------------- 规则模板兜底 ----------------

_FALLBACK_SPACE = {
    "room_type": "客厅",
    "summary": "毛坯房，墙面地面未装修，采光良好",
    "walls": "四面平整墙面，主墙完整可摆放家具",
    "floor": "水泥毛坯地面",
    "windows_doors": "含窗户与入户门，位置常规",
    "lighting": "自然采光",
    "render_hints": "bare unfinished room, empty walls, natural daylight",
}


def _fallback_space(scene: str) -> dict:
    """VLM 不可用时的保守空间描述（scene: living_room/master_bedroom/dining_room）"""
    data = dict(_FALLBACK_SPACE)
    data["room_type"] = {"living_room": "客厅", "master_bedroom": "主卧", "dining_room": "餐厅"}.get(scene, "房间")
    return data


def _extract_json(text: str) -> dict:
    """从模型回复提取 JSON：剥 <think> 思考段与 ``` 围栏；
    依次尝试原文/花括号片段 × 清尾随逗号，兼容大模型常见输出瑕疵"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    candidates = [text]
    s, e = text.find("{"), text.rfind("}")
    if s >= 0 and e > s:
        candidates.append(text[s:e + 1])
    for c in candidates:
        for cleaned in (c, re.sub(r",\s*([}\]])", r"\1", c)):
            try:
                return json.loads(cleaned, strict=False)
            except (json.JSONDecodeError, ValueError):
                continue
    raise json.JSONDecodeError("no valid json in reply", text[:80], 0)


def _fallback_layout(furniture_cn: list[str]) -> dict:
    """LLM 不可用时的静态布局模板：家具逐项给默认摆位"""
    default_pos = {
        "沙发": "靠主墙摆放，面向采光面", "转角沙发": "L 形沿墙布置，留出动线",
        "大床": "床头靠内墙，两侧留床头柜位", "餐桌": "居中摆放，四周留通行距离",
        "电视机": "挂对面主墙，与沙发/床相对", "电视柜": "电视下方沿墙",
        "茶几": "沙发前方居中", "冰箱": "靠角落阴凉侧", "盆栽": "窗边与角落点缀",
        "餐椅": "餐桌四周配套摆放", "餐边柜": "餐桌侧墙", "酒柜": "餐厅角落",
        "床头柜": "大床两侧对称摆放", "五斗柜": "卧室空墙", "梳妆台": "窗侧自然光下",
        "婴儿床": "大床一侧，远离窗户", "书架": "靠墙竖排", "书桌": "靠窗采光位",
        "人体工学椅": "书桌前", "空调": "不直吹床/沙发的墙面高位",
        "洗衣机": "阳台或厨卫角落", "热水器": "厨卫靠水路墙面",
        "微波炉": "橱柜台面", "烤箱": "橱柜嵌入位", "洗碗机": "水槽旁橱柜",
        "地毯": "沙发/床前活动区", "窗帘": "整面窗墙落地帘", "落地灯": "沙发侧角落",
        "装饰挂画": "主墙视平线高度", "全身镜": "玄关或衣柜旁", "跑步机": "阳台或空旷角落",
        "地毯": "沙发区/茶几下方", "衣柜": "沿侧墙整排", "书架": "侧墙展示面",
        "空调": "高处避开床头", "洗衣机": "阳台/角落上下水位",
    }
    arrangement = [
        {"item": name, "position": default_pos.get(name, "按常规动线摆放"), "reason": "常规最佳实践"}
        for name in furniture_cn
    ] or [{"item": "软装", "position": "保持空间整洁留白", "reason": "未选家具"}]
    return {
        "arrangement": arrangement,
        "flow_notes": "以采光面为视觉中心，动线围绕活动区环形展开，通道宽度不小于 60cm。",
        "enriched_prompt": "",
    }


# ---------------- 第一步：看懂空间（VLM 多模态） ----------------

_SPACE_PROMPT = (
    "你是室内设计专家。请分析这张毛坯房照片，只输出 JSON（不要多余文字），结构：\n"
    '{"room_type":"房间类型(客厅/卧室/餐厅等)","summary":"一句话空间概况",'
    '"walls":"墙面状况与可摆家具的主墙位置","floor":"地面现状",'
    '"windows_doors":"门窗位置与朝光面","lighting":"采光情况",'
    '"render_hints":"英文提示词短语，描述该房间结构特征用于图生图，例如 bare concrete walls, large window on the left"}'
)


def _is_cloud_chat_available() -> bool:
    """仅硅基流动云端启用真实 AI 分析（同一 API Key 调 chat/completions）

    取当前用户配置（未配置回退 .env）：用户在前端自填 Key 后无需重启即生效。
    """
    cfg = effective_render()
    return bool(cfg["api_key"]) and "siliconflow" in cfg["base_url"].lower()


async def analyze_space(photo_b64: str, scene: str) -> dict:
    """第一步：VLM 看懂空间。返回结构化空间理解结果（失败走规则模板）。"""
    if not (settings.SPACE_AI_ENABLED and photo_b64 and _is_cloud_chat_available()):
        return _fallback_space(scene)
    try:
        cfg = effective_render()
        async with httpx.AsyncClient(timeout=settings.SPACE_AI_TIMEOUT, trust_env=False) as c:
            r = await c.post(
                f"{cfg['base_url'].rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {cfg['api_key']}"},
                json={
                    "model": settings.SPACE_VLM_MODEL,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{photo_b64}"}},
                            {"type": "text", "text": _SPACE_PROMPT},
                        ],
                    }],
                    "temperature": 0.3,
                    "max_tokens": 600,
                },
            )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"].strip()
            data = _extract_json(text)
            if not isinstance(data, dict) or not data.get("room_type"):
                raise ValueError("bad space json")
            return data
    except Exception as e:
        print(f"[space_ai] 空间理解降级（模板兜底）: {type(e).__name__}: {e}")
        return _fallback_space(scene)


# ---------------- 第二步：构思布局（LLM） ----------------

_LAYOUT_PROMPT = (
    "你是室内布局设计师。空间理解结果：{space}\n"
    "业主提供的家具：{furniture}；装修风格：{style}；房间用途：{scene}。"
    "请规划合理的家具摆放方案（考虑尺寸协调与动线），只输出 JSON（不要多余文字）：\n"
    '{{"arrangement":[{{"item":"家具名","position":"摆放位置(相对门窗/墙面)","reason":"理由"}}],'
    '"flow_notes":"动线说明一句话","enriched_prompt":"英文提示词短语(30词内)描述该布局用于室内渲染图"}}'
)


async def plan_layout(space_result: dict, furniture_cn: list[str], style: str, scene: str) -> dict:
    """第二步：LLM 构思布局。返回摆放方案 + 英文渲染提示词增量（失败走静态模板）。"""
    if not settings.SPACE_AI_ENABLED or not _is_cloud_chat_available():
        return _fallback_layout(furniture_cn)
    style_name = {"modern": "现代简约", "chinese": "新中式", "light": "轻奢风", "wood": "原木风"}.get(style, style)
    scene_name = {"living_room": "客厅", "master_bedroom": "主卧", "dining_room": "餐厅"}.get(scene, scene)
    prompt = _LAYOUT_PROMPT.format(
        space=json.dumps(space_result, ensure_ascii=False),
        furniture="、".join(furniture_cn) or "（业主暂未选定，请给出基础软装建议）",
        style=style_name, scene=scene_name,
    )
    try:
        cfg = effective_render()
        async with httpx.AsyncClient(timeout=settings.SPACE_AI_TIMEOUT, trust_env=False) as c:
            r = await c.post(
                f"{cfg['base_url'].rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {cfg['api_key']}"},
                json={
                    "model": settings.SPACE_LLM_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.5,
                    "max_tokens": 900,
                },
            )
            r.raise_for_status()
            text = r.json()["choices"][0]["message"]["content"].strip()
            data = _extract_json(text)
            if not isinstance(data, dict) or "arrangement" not in data:
                raise ValueError("bad layout json")
            data.setdefault("flow_notes", "")
            data.setdefault("enriched_prompt", "")
            return data
    except Exception as e:
        print(f"[space_ai] 布局规划降级（模板兜底）: {type(e).__name__}: {e}")
        return _fallback_layout(furniture_cn)
