"""Agent Router：只做参数校验、鉴权、调用 Service、返回响应。"""
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_agent_service, get_current_user
from app.core.responses import ok
from app.modules.agent.schemas import ChatRequest
from app.modules.agent.service import AgentService

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post("/chat")
async def chat(payload: ChatRequest, service: AgentService = Depends(get_agent_service),
               user=Depends(get_current_user)):
    return ok(await service.chat(payload, user))


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest, service: AgentService = Depends(get_agent_service),
                      user=Depends(get_current_user)):
    async def event_generator():
        async for event in service.stream_chat(payload, user):
            yield f"data: {event.model_dump_json()}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
