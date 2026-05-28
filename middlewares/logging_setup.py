import logging
import os
from logging.handlers import RotatingFileHandler

from pythonjsonlogger.jsonlogger import JsonFormatter


def _get_text_formatter():
    return logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _get_json_formatter():
    return JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s %(correlation_id)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    )


def setup_logging(log_level: str = "INFO", log_format: str = "text") -> None:
    """Configure root logger to write to both console and logs/app.log.

    RotatingFileHandler caps each file at 10 MB and keeps the last 5 rotated
    files (app.log, app.log.1 … app.log.5) so the directory never grows unbounded.

    When LOG_FORMAT=json is set, logs are emitted as structured JSON for
    ingestion by Datadog, CloudWatch, ELK, etc.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    use_json = log_format.lower() == "json"
    fmt = _get_json_formatter() if use_json else _get_text_formatter()

    os.makedirs("logs", exist_ok=True)

    console = logging.StreamHandler()
    console.setFormatter(fmt)

    file_handler = RotatingFileHandler(
        "logs/app.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB per file
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)

    logging.basicConfig(level=level, handlers=[console, file_handler])
