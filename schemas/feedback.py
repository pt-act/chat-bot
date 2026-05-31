"""Typed models for persistent answer feedback (#3)."""

from typing import Literal

from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    """A thumbs-up/down on an answer, optionally with a reason and a Q/A snapshot."""

    rating: Literal["up", "down"] = Field(examples=["down"])
    reason: str | None = Field(default=None, max_length=2000, examples=["Cited the wrong policy."])
    correlation_id: str | None = Field(
        default=None, description="Correlation id of the rated turn; captured from the request when omitted."
    )
    question: str | None = Field(default=None, examples=["What is the return window?"])
    answer: str | None = Field(default=None, examples=["Returns are accepted within 30 days."])


class FeedbackResponse(BaseModel):
    feedback_id: str = Field(examples=["a1b2c3d4e5f6"])
    rating: str = Field(examples=["down"])
    status: str = Field(default="recorded", examples=["recorded"])


class FeedbackEntry(BaseModel):
    feedback_id: str
    rating: str
    reason: str | None = None
    correlation_id: str | None = None
    question: str | None = None
    answer: str | None = None
    created_at: str | None = None


class FeedbackListResponse(BaseModel):
    total: int
    feedback: list[FeedbackEntry]
    next_cursor: str | None = Field(
        default=None, description="Opaque cursor for the next page, or null when exhausted."
    )
