FROM python:3.10-slim AS base

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user (least privilege). Pre-create the runtime dirs the app writes
# to (logs, Chroma store, staged uploads) and hand ownership to the unprivileged user;
# named volumes initialize from this ownership so queue-mode uploads remain writable.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/logs /app/chroma_db /app/ingest_incoming \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]


FROM base AS test

# Dev deps need root to install; drop back to the unprivileged user to run tests.
USER root
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt httpx ruff \
    && chown -R appuser:appuser /app
USER appuser

CMD ["pytest", "-v"]
