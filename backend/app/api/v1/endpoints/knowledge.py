"""知识端点：检索 / 索引任务（RAG 独立服务门面）。"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.rbac import get_current_user
from app.core.responses import ok
from app.modules.agent.rag.indexer import Indexer
from app.modules.agent.rag.service import RagService

router = APIRouter(tags=["knowledge"])
_rag = RagService()
_indexer = Indexer()


class SearchBody(BaseModel):
    query: str
    top_k: int = 5


class IndexBody(BaseModel):
    doc_id: str
    content: str = ""


@router.post("/knowledge/search")
async def knowledge_search(body: SearchBody, user=Depends(get_current_user)):
    return ok(await _rag.retrieve(body.query, user, top_k=body.top_k))


@router.post("/knowledge/index")
async def knowledge_index(body: IndexBody, user=Depends(get_current_user)):
    return ok(await _indexer.index_document(body.doc_id, body.content))
