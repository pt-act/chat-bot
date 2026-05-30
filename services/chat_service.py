from functools import lru_cache

from config import get_settings
from graph.builder import build_graph

_graph = lru_cache(maxsize=1)(build_graph)


def conversation(
    user_id: str,
    q: str,
    mode: str | None = None,
    lang: str = "auto",
    top_k: int | None = None,
    score_threshold: float | None = None,
):
    """Run the chat graph for one turn.

    `mode`/`lang`/`top_k`/`score_threshold` are optional per-request overrides;
    when omitted the server defaults (config) and auto language detection apply.
    """
    chat_mode = (mode or get_settings().chat_mode).lower()
    state: dict = {"user_id": user_id, "question": q, "chat_mode": chat_mode}
    if lang and lang != "auto":
        state["lang"] = lang
    if top_k is not None:
        state["top_k"] = top_k
    if score_threshold is not None:
        state["score_threshold"] = score_threshold

    result = _graph().invoke(state)

    resolved = result.get("lang")  # "English"/"Arabic" set by generate_answer
    return {
        "answer": result["messages"][-1].content,
        "sources": result.get("sources", []),
        "self_ingested": result.get("self_ingested", False),
        "lang": "ar" if resolved == "Arabic" else "en",
    }
