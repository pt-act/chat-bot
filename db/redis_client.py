from functools import lru_cache

import redis as _redis

from config import get_settings

# Namespace prefix for per-user conversation memory. Keeps user-controlled ids
# from colliding with operational keys (e.g. "ingest:doc_ids", "rate_limit:*").
_MEMORY_PREFIX = "chat:memory:"


def memory_key(user_id: str) -> str:
    """Return the namespaced Redis key for a user's conversation memory."""
    return f"{_MEMORY_PREFIX}{user_id}"


@lru_cache
def get_redis() -> _redis.Redis:
    setting = get_settings()
    return _redis.Redis(
        host=setting.redis_host,
        port=setting.redis_port,
        password=setting.redis_password or None,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
