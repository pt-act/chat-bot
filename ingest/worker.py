"""Durable ingest worker (#4) — ``python -m ingest.worker``.

Consumes ingest jobs from the Redis queue (see ingest.queue) and processes them with
retries + idempotency, so ingestion survives API restarts. Enable with
``INGEST_MODE=queue`` and run this as a separate process (see the ``worker`` service in
docker-compose.yml). A no-op in ``inline`` mode deployments.
"""

import logging
import signal

from config import get_settings
from ingest.queue import process_one
from middlewares.logging_setup import setup_logging

logger = logging.getLogger(__name__)

_running = True


def _stop(*_args):
    global _running
    _running = False


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_format)
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    logger.info("Ingest worker started (ingest_mode=%s)", settings.ingest_mode)

    while _running:
        try:
            process_one()
        except Exception:  # pragma: no cover - defensive: a poison job must not kill the loop
            logger.exception("Worker loop error; continuing")

    logger.info("Ingest worker stopped")


if __name__ == "__main__":  # pragma: no cover - process entrypoint
    main()
