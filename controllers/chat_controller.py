import logging
import re

from fastapi import APIRouter, Header, HTTPException

from schemas.chat import ChatRequest
from services.chat_service import conversation

logger = logging.getLogger(__name__)
router = APIRouter()

# X-User-Id is used to scope per-user conversation memory. Constrain it to a safe,
# bounded character set so a caller cannot craft a value that breaks key namespacing
# or bloats Redis. Memory keys are additionally namespaced (see db.redis_client).
_USER_ID_RE = re.compile(r"^[A-Za-z0-9_.@-]{1,128}$")


def _validate_user_id(x_user_id: str) -> str:
    user_id = (x_user_id or "").strip()
    if not user_id:
        return "anonymous"
    if not _USER_ID_RE.match(user_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid X-User-Id: use 1-128 chars from [A-Za-z0-9_.@-]",
        )
    return user_id


@router.post("/chat")
def chat_controller(
    request: ChatRequest,
    x_user_id: str = Header(default="anonymous"),
):
    user_id = _validate_user_id(x_user_id)
    try:
        result = conversation(user_id=user_id, q=request.q)
        logger.info("Chat response generated for user %s", user_id)
        # Legacy contract: sources are bare label strings (v1 returns structured objects).
        sources = [s.get("label", "unknown") if isinstance(s, dict) else s for s in result["sources"]]
        return {"status": "success", "data": result["answer"], "sources": sources}
    except ValueError as e:
        # 4xx validation feedback is safe to surface to the caller.
        logger.warning("Chat validation error for user %s: %s", user_id, e)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        # Log detail server-side; return a generic message (no internal text leak).
        logger.error("Chat runtime error for user %s: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Failed to generate a response") from e
    except Exception:
        logger.exception("Chat failed for user %s", user_id)
        raise HTTPException(status_code=500, detail="Failed to generate a response")
