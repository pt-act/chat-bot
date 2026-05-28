import logging

from fastapi import APIRouter, Header, HTTPException

from schemas.chat import ChatRequest
from services.chat_service import conversation

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/chat")
def chat_controller(
    request: ChatRequest,
    x_user_id: str = Header(default="anonymous"),
):
    try:
        result = conversation(user_id=x_user_id, q=request.q)
        logger.info("Chat response generated for user %s", x_user_id)
        return {"status": "success", "data": result["answer"], "sources": result["sources"]}
    except Exception:
        logger.exception("Chat failed for user %s", x_user_id)
        raise HTTPException(status_code=500, detail="Failed to generate a response")
