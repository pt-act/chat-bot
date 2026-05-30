import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import get_settings
from controllers.chat_controller import router as chat_router
from controllers.ingest_controller import router as ingest_router
from db.redis_client import get_redis
from db.vector import get_vectorstore
from middlewares.logging_setup import setup_logging
from middlewares.observability import (
    CorrelationIdFilter,
    CorrelationIdMiddleware,
    RequestTimingMiddleware,
)
from middlewares.rate_limiter import RateLimitMiddleware

settings = get_settings()
setup_logging(settings.log_level, settings.log_format)

# Install correlation ID filter on root logger so every log line gets it
logging.getLogger().addFilter(CorrelationIdFilter())

logger = logging.getLogger(__name__)

_redis_ok = False
_chroma_ok = False


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


app = FastAPI(title="Chatbot API", version="1.0.0", lifespan=lifespan)

# Observability (outermost — captures everything)
app.add_middleware(CorrelationIdMiddleware)
app.add_middleware(RequestTimingMiddleware)

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

app.include_router(ingest_router, prefix="/api")
app.include_router(chat_router, prefix="/api")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [{"field": e["loc"][-1], "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"error": "Validation failed", "details": errors})


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    logger.warning("Value error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=400, content={"error": "Bad request", "detail": str(exc)})


@app.exception_handler(RuntimeError)
async def runtime_error_handler(request: Request, exc: RuntimeError):
    # Log the full detail server-side, but never echo internal error text to the
    # client — it can leak file paths, upstream messages, or infra detail.
    logger.error("Runtime error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


@app.get("/health")
def health_check():
    deps = {"redis": "ok" if _redis_ok else "unavailable", "chromadb": "ok" if _chroma_ok else "unavailable"}
    status = "ok" if (_redis_ok and _chroma_ok) else "degraded"
    return {"status": status, "dependencies": deps}


@app.get("/ready")
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


@app.get("/")
def home():
    return {"message": "Chatbot Running"}
