"""Typed models for the learning-mode review workflow (two-phase ingest)."""

from pydantic import BaseModel, Field


class PendingReview(BaseModel):
    """A model-synthesized answer awaiting human review before it is embedded."""

    entry_id: str = Field(examples=["synthesized:1a2b3c4d5e6f"])
    question: str = Field(examples=["What is your warranty period?"])
    answer: str = Field(examples=["Based on my knowledge, warranties typically last 12 months..."])
    best_score: float | None = Field(default=None, ge=0, le=1, examples=[0.12])
    created_at: str | None = Field(default=None, examples=["2026-05-31T10:15:00Z"])
    status: str = Field(default="pending", examples=["pending"])


class PendingListResponse(BaseModel):
    total: int
    pending: list[PendingReview]
    next_cursor: str | None = Field(
        default=None, description="Opaque cursor for the next page, or null when exhausted."
    )


class ReviewDecision(BaseModel):
    entry_id: str
    status: str = Field(examples=["approved", "rejected"])
    embedded: bool = Field(default=False, description="True when the entry was embedded into the synthesized store.")
