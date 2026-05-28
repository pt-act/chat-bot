import logging

from fastapi import HTTPException, Request
from fastapi.security import APIKeyHeader

from config import get_settings

logger = logging.getLogger(__name__)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class AuthenticationError(HTTPException):
    def __init__(self):
        super().__init__(status_code=401, detail="Invalid or missing API key")


async def require_api_key(request: Request) -> str | None:
    """
    FastAPI dependency for API-key authentication.

    - If API_KEY is not configured (empty), skip validation (local dev mode).
    - DELETE /ingest/{doc_id} ALWAYS requires the key regardless of dev mode.
    - Other endpoints require it only when REQUIRE_AUTH_FOR_INGEST=true.
    """
    settings = get_settings()
    provided = await api_key_header(request)

    # DELETE always requires auth
    is_delete = request.method == "DELETE"

    # Check if auth is required for this endpoint
    requires_auth = is_delete or settings.require_auth_for_ingest

    if not requires_auth:
        return None

    if not settings.api_key:
        logger.warning("Auth required but API_KEY is not configured")
        raise AuthenticationError()

    if provided != settings.api_key:
        logger.warning("Invalid API key provided")
        raise AuthenticationError()

    return provided
