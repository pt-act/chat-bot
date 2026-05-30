import logging
from collections.abc import Iterator
from functools import lru_cache

from langchain_core.messages import AIMessage, HumanMessage

from config import get_settings
from graph.builder import build_graph
from graph.nodes.generate_answer import build_chat_prompt
from graph.nodes.load_memory import load_memory
from graph.nodes.retrieve_context import retrieve_context
from graph.nodes.self_ingest import self_ingest
from graph.nodes.store_memory import store_memory
from graph.nodes.summarize import summarize
from utils.llm_adapter import get_llm

logger = logging.getLogger(__name__)

_graph = lru_cache(maxsize=1)(build_graph)


def _initial_state(user_id, q, mode, lang, top_k, score_threshold) -> dict:
    chat_mode = (mode or get_settings().chat_mode).lower()
    state: dict = {"user_id": user_id, "question": q, "chat_mode": chat_mode}
    if lang and lang != "auto":
        state["lang"] = lang
    if top_k is not None:
        state["top_k"] = top_k
    if score_threshold is not None:
        state["score_threshold"] = score_threshold
    return state


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
    state = _initial_state(user_id, q, mode, lang, top_k, score_threshold)
    result = _graph().invoke(state)

    resolved = result.get("lang")  # "English"/"Arabic" set by generate_answer
    return {
        "answer": result["messages"][-1].content,
        "sources": result.get("sources", []),
        "self_ingested": result.get("self_ingested", False),
        "lang": "ar" if resolved == "Arabic" else "en",
    }


def stream_conversation(
    user_id: str,
    q: str,
    mode: str | None = None,
    lang: str = "auto",
    top_k: int | None = None,
    score_threshold: float | None = None,
) -> Iterator[tuple[str, dict]]:
    """Yield (event, data) pairs for a streaming chat turn.

    Pre-steps (load memory, retrieve context) run synchronously; the LLM answer is
    streamed token-by-token; post-steps (self-ingest, summarize, store memory) run
    after the stream so memory is persisted even though the client saw tokens first.

    Events: ``token`` {delta}, ``sources`` {sources}, ``done`` {meta}. Errors are
    surfaced by the caller as an ``error`` event.
    """
    state = _initial_state(user_id, q, mode, lang, top_k, score_threshold)
    state.update(load_memory(state))
    state.update(retrieve_context(state))

    prompt, resolved_lang = build_chat_prompt(state)

    parts: list[str] = []
    for chunk in get_llm(temperature=0, max_tokens=512).stream(prompt):
        delta = getattr(chunk, "content", "") or ""
        if delta:
            parts.append(delta)
            yield "token", {"delta": delta}
    answer = "".join(parts)

    # Reconstruct the state generate_answer would have produced, then run post-steps.
    state["messages"] = (state.get("messages") or []) + [HumanMessage(content=q), AIMessage(content=answer)]
    state["last_answer"] = answer
    state["lang"] = resolved_lang

    yield "sources", {"sources": state.get("sources", [])}

    try:
        state.update(self_ingest(state))
        state.update(summarize(state))
        store_memory(state)
    except Exception:  # pragma: no cover - defensive; never fail the stream on post-steps
        logger.exception("Streaming post-steps failed for user %s", user_id)

    yield (
        "done",
        {
            "meta": {
                "mode": state["chat_mode"],
                "lang": "ar" if resolved_lang == "Arabic" else "en",
                "self_ingested": state.get("self_ingested", False),
                "model": get_settings().llm_model,
            }
        },
    )
