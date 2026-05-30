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
    # Per-request overrides (optional; fall back to server defaults)
    lang: str  # input: "auto"|"en"|"ar"; after generate: resolved label "English"/"Arabic"
    top_k: int
    score_threshold: float
