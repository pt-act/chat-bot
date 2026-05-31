"""RFC 9457 (problem+json) error model, applied application-wide.

Replaces the previously inconsistent error bodies ({"error","detail"},
{"error","details"}, FastAPI's {"detail"}) with a single, documented shape. 5xx
responses never echo internal exception text (see audit finding M-3); full detail is
logged server-side with the request correlation id.
"""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from middlewares.observability import correlation_id_var

logger = logging.getLogger(__name__)

_PROBLEM_CONTENT_TYPE = "application/problem+json"
_TYPE_BASE = "https://errors.chat-bot"


def problem_response(
    status: int,
    title: str,
    detail: str | None = None,
    type_: str = "about:blank",
    errors: list[dict] | None = None,
) -> JSONResponse:
    body = {
        "type": type_,
        "title": title,
        "status": status,
        "detail": detail,
        "correlation_id": correlation_id_var.get() or None,
        "errors": errors,
    }
    # Drop null optional members for a tidy payload.
    body = {k: v for k, v in body.items() if v is not None}
    return JSONResponse(status_code=status, content=body, media_type=_PROBLEM_CONTENT_TYPE)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        errors = [{"field": e["loc"][-1], "message": e["msg"]} for e in exc.errors()]
        return problem_response(422, "Validation failed", type_=f"{_TYPE_BASE}/validation", errors=errors)

    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException):
        # Preserve caller-provided status/detail (4xx are safe; controllers already
        # genericize their own 5xx detail before raising).
        title = "Error" if exc.status_code >= 500 else "Request failed"
        return problem_response(exc.status_code, title, detail=str(exc.detail))

    @app.exception_handler(ValueError)
    async def _value(request: Request, exc: ValueError):
        logger.warning("Value error on %s %s: %s", request.method, request.url.path, exc)
        return problem_response(400, "Bad request", detail=str(exc), type_=f"{_TYPE_BASE}/bad-request")

    @app.exception_handler(RuntimeError)
    async def _runtime(request: Request, exc: RuntimeError):
        # Log detail server-side; never echo internal text to the client (M-3).
        logger.error("Runtime error on %s %s: %s", request.method, request.url.path, exc)
        return problem_response(500, "Internal server error")

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return problem_response(500, "Internal server error")
