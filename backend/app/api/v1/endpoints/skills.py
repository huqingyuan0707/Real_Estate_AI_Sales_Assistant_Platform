"""Skill 市场接口：列表 / 安装 / 卸载 / 调用（SSE，对齐 5.2 POST /skills/{id}/invoke）"""
import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.responses import fail, ok
from app.core.exceptions import ErrorCode
from app.mock_data import SKILLS
from app.schemas.requests import SkillInvokeRequest
from app.services.llm import LLMUnavailable, llm_available, llm_stream

router = APIRouter()

# 技能 → 生成提示词（文案类技能走 LLM 流式；其余引导到对应功能页）
SKILL_PROMPTS = {
    "文案生成": (
        "你是资深房产销售文案专家。根据房源信息，输出三个版本：\n"
        "【朋友圈】80字内带emoji\n【短视频口播】15秒口播稿\n【客户话术】一段面对面介绍\n"
        "结尾提醒：文案仅供营销参考，价格/承诺以官方口径为准。"
    ),
    "政策问答": (
        "你是房产政策顾问。基于你了解的通用规则回答，并提醒：政策以当地最新官方文件为准。"
    ),
    "风水分析": (
        "你是风水参考顾问。从传统居住舒适度视角给出朝向/格局参考分析，"
        "并提醒：内容仅为民俗参考，请理性看待。"
    ),
    "竞品对比": (
        "你是楼盘对比分析师。根据输入的两个以上楼盘参数，输出对比要点与一句话结论。"
    ),
}
# 引导类技能：不在对话里硬做，SSE 返回引导话术（与前端功能页形成闭环）
SKILL_GUIDE = {
    "户型解析": "户型解析需要在【户型工具】页上传户型图/DXF，完成后可人工修正识别结果。",
    "效果图渲染": "效果图渲染请在【AI 空间智能引擎】页上传毛坯照片并定制家具/墙色后一键生成。",
}


def _sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


@router.get("")
def list_skills():
    return ok(SKILLS)


@router.post("/{skill_id}/install")
def install_skill(skill_id: str):
    skill = next((s for s in SKILLS if s["id"] == skill_id), None)
    if not skill:
        return fail(ErrorCode.NOT_FOUND, "Skill 不存在", 404)
    skill["installed"] = True
    return ok(skill, "安装成功")


@router.delete("/{skill_id}/install")
def uninstall_skill(skill_id: str):
    skill = next((s for s in SKILLS if s["id"] == skill_id), None)
    if not skill:
        return fail(ErrorCode.NOT_FOUND, "Skill 不存在", 404)
    if skill["name"] == "效果图渲染":  # 演示：任务占用时不可卸载
        return fail(ErrorCode.RATE_LIMITED, "该技能正在执行任务，请稍后重试", 429)
    skill["installed"] = False
    return ok(skill, "已卸载")


@router.post("/{skill_id}/invoke")
async def invoke_skill(skill_id: str, body: SkillInvokeRequest):
    """调用 Skill（SSE 流式）：文案/政策/风水/竞品走 LLM，解析/渲染引导到功能页"""
    skill = next((s for s in SKILLS if s["id"] == skill_id), None)
    if not skill:
        return fail(ErrorCode.NOT_FOUND, "Skill 不存在", 404)
    if not skill["installed"]:
        return fail(ErrorCode.FORBIDDEN, "该 Skill 未安装，请先在市场安装", 403)

    name = skill["name"]

    async def _gen():
        yield _sse("phase", f"正在调用技能「{name}」...")

        # 引导类技能：返回跳转话术（演示环境不开后台解析进程）
        if name in SKILL_GUIDE:
            yield _sse("message", SKILL_GUIDE[name])
            yield _sse("done", json.dumps({"skill": name, "guide": True}, ensure_ascii=False))
            return

        system = SKILL_PROMPTS.get(name, "你是房产销售 AI 助手，简洁专业地回答。")
        if not await llm_available():
            # LLM 未接入：演示模式同一 SSE 协议
            yield _sse("phase", "⚙️ 演示模式生成中...")
            demo = (f"【{name} · 演示模式】\n\n"
                    f"已收到输入：{body.input[:60]}\n\n"
                    "接入 LLM（backend/.env 配 Ollama 或 API Key）后此处输出真实生成内容。")
            for i in range(0, len(demo), 8):
                yield _sse("message", demo[i:i + 8])
                await asyncio.sleep(0.03)
            yield _sse("done", json.dumps({"skill": name, "model": "demo"}, ensure_ascii=False))
            return

        yield _sse("phase", "✍️ 生成中...")
        try:
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": body.input},
            ]
            async for piece in llm_stream(messages):
                yield _sse("message", piece)
            yield _sse("done", json.dumps({"skill": name, "model": "llm"}, ensure_ascii=False))
        except LLMUnavailable:
            yield _sse("error", json.dumps({"code": ErrorCode.THIRD_PARTY_TIMEOUT, "msg": "模型服务中断，请稍后重试"}, ensure_ascii=False))

    return StreamingResponse(_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
