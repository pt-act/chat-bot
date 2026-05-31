"""v1 chat controller — typed response envelope (ChatResponse) + SSE streaming."""

import json
import logging

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse

from config import get_settings
from controllers.chat_controller import _validate_user_id
from guardrails import GuardrailViolation
from middlewares.observability import correlation_id_var
from schemas.chat import ChatRequest
from schemas.responses import ChatMeta, ChatResponse, Source
from services.chat_service import conversation, stream_conversation

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Ask the bot a question",
    description=(
        "Runs the RAG pipeline and returns the answer with structured citations and "
        "response metadata (mode, model, correlation id, self-ingest flag)."
    ),
)
def chat(request: ChatRequest, x_user_id: str = Header(default="anonymous")) -> ChatResponse:
    user_id = _validate_user_id(x_user_id)
    settings = get_settings()
    try:
        result = conversation(
            user_id=user_id,
            q=request.q,
            mode=request.mode,
            lang=request.lang,
            top_k=request.top_k,
            score_threshold=request.score_threshold,
        )
    except ValueError as e:
        logger.warning("Chat validation error for user %s: %s", user_id, e)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except RuntimeError as e:
        logger.error("Chat runtime error for user %s: %s", user_id, e)
        raise HTTPException(status_code=500, detail="Failed to generate a response") from e

    logger.info("Chat response generated for user %s", user_id)
    sources = [_to_source(s) for s in result.get("sources", [])]
    return ChatResponse(
        answer=result["answer"],
        sources=sources,
        meta=ChatMeta(
            mode=(request.mode or settings.chat_mode).lower(),
            lang=result.get("lang"),
            self_ingested=result.get("self_ingested", False),
            grounded=result.get("grounded"),
            grounded_score=result.get("grounded_score"),
            correlation_id=correlation_id_var.get() or None,
            model=settings.llm_model,
        ),
    )


def _to_source(s) -> Source:
    """Accept either a structured citation dict or a bare label string."""
    if isinstance(s, Source):
        return s
    if isinstance(s, dict):
        return Source(**{k: v for k, v in s.items() if k in Source.model_fields})
    return Source(label=str(s))


@router.post(
    "/chat/stream",
    summary="Ask the bot a question (streaming, SSE)",
    description=(
        "Same as `POST /chat` but streams the answer as Server-Sent Events: "
        "`token` (incremental deltas), then `sources`, then `done` (meta). On failure "
        "an `error` event is emitted."
    ),
    responses={200: {"content": {"text/event-stream": {}}}},
)
def chat_stream(request: ChatRequest, x_user_id: str = Header(default="anonymous")) -> StreamingResponse:
    user_id = _validate_user_id(x_user_id)

    def event_gen():
        try:
            for event, data in stream_conversation(
                user_id=user_id,
                q=request.q,
                mode=request.mode,
                lang=request.lang,
                top_k=request.top_k,
                score_threshold=request.score_threshold,
            ):
                if event == "done":
                    data["meta"]["correlation_id"] = correlation_id_var.get() or None
                yield _sse(event, data)
        except GuardrailViolation as e:
            logger.warning("Streaming chat blocked by guardrail for user %s: %s", user_id, e)
            yield _sse("error", {"title": str(e), "status": 400, "reason": e.reason})
        except Exception:
            logger.exception("Streaming chat failed for user %s", user_id)
            yield _sse("error", {"title": "Internal server error", "status": 500})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
