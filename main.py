import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import get_settings
from controllers.chat_controller import router as legacy_chat_router
from controllers.ingest_controller import router as legacy_ingest_router
from controllers.v1.chat import router as v1_chat_router
from controllers.v1.feedback import router as v1_feedback_router
from controllers.v1.ingest import router as v1_ingest_router
from controllers.v1.review import router as v1_review_router
from db.redis_client import get_redis
from db.vector import get_vectorstore
from middlewares.errors import register_error_handlers
from middlewares.logging_setup import setup_logging
from middlewares.observability import (
    CorrelationIdFilter,
    CorrelationIdMiddleware,
    RequestTimingMiddleware,
)
from middlewares.rate_limiter import RateLimitMiddleware
from schemas.responses import DependencyHealth

settings = get_settings()
setup_logging(settings.log_level, settings.log_format)

# Install correlation ID filter on root logger so every log line gets it
logging.getLogger().addFilter(CorrelationIdFilter())

logger = logging.getLogger(__name__)

_redis_ok = False
_chroma_ok = False

# Legacy unversioned prefix kept for one deprecation cycle; new clients use /api/v1.
_LEGACY_PREFIX = "/api"
_V1_PREFIX = "/api/v1"
_SUNSET = "Sat, 01 Nov 2025 00:00:00 GMT"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis_ok, _chroma_ok

    try:
        get_redis().ping()
        _redis_ok = True
        logger.info("Redis connected")
    except Exception as e:
        _redis_ok = False
        logger.error("Redis connection failed: %s", e)

    try:
        get_vectorstore().similarity_search("health", k=1)
        _chroma_ok = True
        logger.info("ChromaDB connected")
    except Exception as e:
        _chroma_ok = False
        logger.error("ChromaDB connection failed: %s", e)

    yield

    logger.info("Shutting down...")


app = FastAPI(
    title="Chatbot API",
    version="2.4.0",
    description=(
        "RAG chatbot API. Versioned endpoints live under `/api/v1` and return typed "
        "envelopes; errors use RFC 9457 (application/problem+json). The unversioned "
        "`/api` paths are deprecated and kept for one cycle."
    ),
    license_info={"name": "MIT"},
    openapi_tags=[
        {"name": "chat", "description": "Conversational RAG endpoints."},
        {"name": "ingest", "description": "Document ingestion and management."},
        {"name": "review", "description": "Moderate learning-mode synthesized answers (two-phase ingest)."},
        {"name": "feedback", "description": "Capture and review 👍/👎 feedback on answers."},
        {"name": "system", "description": "Health and readiness probes."},
    ],
    lifespan=lifespan,
)


class DeprecationHeaderMiddleware(BaseHTTPMiddleware):
    """Mark legacy unversioned `/api/*` responses as deprecated (RFC 8594)."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path.startswith(_LEGACY_PREFIX + "/") and not path.startswith(_V1_PREFIX):
            response.headers["Deprecation"] = "true"
            response.headers["Sunset"] = _SUNSET
            response.headers["Link"] = f'<{_V1_PREFIX}>; rel="successor-version"'
        return response


# Observability (outermost — captures everything)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(RequestTimingMiddleware)
app.add_middleware(DeprecationHeaderMiddleware)

# Rate limiting
app.add_middleware(RateLimitMiddleware, max_requests=60, window_seconds=60)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# v1 (typed envelopes) + legacy (unversioned, deprecated)
app.include_router(v1_ingest_router, prefix=_V1_PREFIX)
app.include_router(v1_chat_router, prefix=_V1_PREFIX)
app.include_router(v1_review_router, prefix=_V1_PREFIX)
app.include_router(v1_feedback_router, prefix=_V1_PREFIX)
app.include_router(legacy_ingest_router, prefix=_LEGACY_PREFIX)
app.include_router(legacy_chat_router, prefix=_LEGACY_PREFIX)

# Unified RFC 9457 problem+json error model (application-wide)
register_error_handlers(app)


@app.get("/health", response_model=DependencyHealth, tags=["system"])
def health_check():
    deps = {"redis": "ok" if _redis_ok else "unavailable", "chromadb": "ok" if _chroma_ok else "unavailable"}
    status = "ok" if (_redis_ok and _chroma_ok) else "degraded"
    return {"status": status, "dependencies": deps}


@app.get("/ready", tags=["system"])
def readiness_check():
    """Live readiness probe — checks actual connectivity right now."""
    deps = {}
    all_ok = True

    try:
        get_redis().ping()
        deps["redis"] = "ok"
    except Exception as e:
        deps["redis"] = f"unavailable: {e}"
        all_ok = False

    try:
        get_vectorstore().similarity_search("health", k=1)
        deps["chromadb"] = "ok"
    except Exception as e:
        deps["chromadb"] = f"unavailable: {e}"
        all_ok = False

    status_code = 200 if all_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ready" if all_ok else "not_ready", "dependencies": deps},
    )


@app.get("/", tags=["system"])
def home():
    return {"message": "Chatbot Running"}
