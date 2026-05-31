from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict


class State(TypedDict, total=False):
    user_id: str
    question: str
    messages: list[BaseMessage]
    docs: str
    summary: str
    sources: list[dict]  # structured citations: {label, doc_id, score, page, snippet}
    chat_mode: str
    best_score: float
    last_answer: str
    self_ingested: bool
    pending_review: bool  # learning mode: answer queued for review instead of embedded
    review_entry_id: str  # id of the queued pending-review entry, when applicable
    # Per-request overrides (optional; fall back to server defaults)
    lang: str  # input: "auto"|"en"|"ar"; after generate: resolved label "English"/"Arabic"
    top_k: int
    score_threshold: float
