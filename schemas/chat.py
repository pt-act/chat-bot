from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    q: str
    # Per-request overrides (all optional; omitted → server defaults / auto).
    mode: Literal["strict", "open", "learning", "learning_review"] | None = Field(
        default=None,
        description=(
            "Override the server's default chat mode for this request. 'learning_review' "
            "behaves like 'learning' but queues synthesized answers for human approval."
        ),
    )
    lang: Literal["auto", "en", "ar", "pt"] = Field(
        default="auto",
        description="Force the response language ('pt' = European Portuguese), or auto-detect.",
    )
    top_k: int | None = Field(default=None, ge=1, le=10, description="Number of chunks to retrieve.")
    score_threshold: float | None = Field(
        default=None, ge=0, le=1, description="Minimum relevance score for a chunk to be used."
    )

    @field_validator("q")
    @classmethod
    def question_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Question cannot be empty")
        if len(v) > 2000:
            raise ValueError("Question too long (max 2000 characters)")
        return v
