"""户型解析接口：/house/parse（图片/DXF）+ HITL 人工确认（技术方案 5.2）"""
import uuid

from fastapi import APIRouter

from app.core.responses import ok
from app.mock_data import HOUSE_STRUCT
from app.schemas.requests import HouseConfirmRequest

router = APIRouter()


@router.post("/parse")
async def parse_house():
    """解析 Mock：直接返回 pending_human_confirm 状态与结构化参数，
    前端凭 task_id 渲染人工修正界面。"""
    return ok({**HOUSE_STRUCT, "task_id": f"house-{uuid.uuid4().hex[:6]}"})


@router.post("/parse/{task_id}/confirm")
def confirm_house(task_id: str, body: HouseConfirmRequest):
    """HITL 确认：接收人工修正后的 house_struct，进入规则校验（Mock 恒通过）。"""
    return ok({"task_id": task_id, "status": "confirmed", "house_struct": body.house_struct}, "已确认，规则校验通过")
