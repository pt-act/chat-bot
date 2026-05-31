"""Typed response models for the v1 API.

Centralizes the success envelope and the RFC 9457 (problem+json) error model so
clients have a single, self-describing contract and OpenAPI/SDK codegen is accurate.
"""

from pydantic import BaseModel, Field


class Source(BaseModel):
    """A single retrieved citation backing an answer."""

    label: str = Field(examples=["return_policy.pdf"])
    doc_id: str | None = Field(default=None, examples=["return_policy"])
    score: float | None = Field(default=None, ge=0, le=1, examples=[0.82])
    page: int | None = Field(default=None, examples=[3])
    snippet: str | None = Field(default=None, examples=["Customers may return any item..."])


class TokenUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class ChatMeta(BaseModel):
    mode: str = Field(examples=["strict"])
    lang: str | None = Field(default=None, examples=["en"])
    self_ingested: bool = False
    grounded: str | None = Field(
        default=None,
        description="Groundedness verdict vs. retrieved chunks: supported | partial | unsupported (#2).",
        examples=["supported"],
    )
    grounded_score: float | None = Field(
        default=None, ge=0, le=1, description="Fraction of answer sentences supported by the context.", examples=[0.83]
    )
    correlation_id: str | None = None
    model: str | None = Field(default=None, examples=["gpt-4o-mini"])
    usage: TokenUsage | None = None


class ChatResponse(BaseModel):
    answer: str = Field(examples=["Returns are accepted within 30 days of purchase."])
    sources: list[Source] = []
    meta: ChatMeta


class IngestResult(BaseModel):
    doc_id: str
    status: str = Field(examples=["done", "queued", "skipped"])
    version: str | None = None
    added: int | None = None
    removed: int | None = None
    total: int | None = None
    reason: str | None = None


class DocsListResponse(BaseModel):
    total: int
    docs: list[dict]
    next_cursor: str | None = Field(
        default=None, description="Opaque cursor for the next page, or null when exhausted."
    )


class DeleteResponse(BaseModel):
    status: str = Field(examples=["deleted"])
    doc_id: str


class DependencyHealth(BaseModel):
    status: str = Field(examples=["ok", "degraded"])
    dependencies: dict[str, str] = Field(examples=[{"redis": "ok", "chromadb": "ok"}])


class ProblemDetail(BaseModel):
    """RFC 9457 problem+json error body."""

    type: str = Field(default="about:blank", examples=["https://errors.chat-bot/validation"])
    title: str = Field(examples=["Validation failed"])
    status: int = Field(examples=[422])
    detail: str | None = Field(default=None, examples=["Question cannot be empty"])
    correlation_id: str | None = None
    errors: list[dict] | None = Field(default=None, description="Field-level validation errors, when applicable.")
