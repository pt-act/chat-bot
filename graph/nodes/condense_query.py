"""Context-aware query rewriting (#1).

Retrieval should search on a *self-contained* query, not the raw last message. A turn
like "and what about damaged ones?" embeds to nothing useful, so MMR returns noise and
strict mode may falsely refuse a question the KB can answer. This node condenses the
follow-up into a standalone query using the rolling summary + recent turns, and stores it
in ``state["search_query"]``. `retrieve_context` searches on that; generation still uses
the original ``state["question"]``.

Cheap by construction: skipped on the first turn (no memory), gated by
``query_rewrite_enabled``, capped at 64 output tokens, and wrapped in the provider
resilience layer (#14).
"""

import logging
from functools import lru_cache

from langchain_core.messages import HumanMessage

from config import get_settings
from prompts.condense import build_condense_prompt
from utils.llm_adapter import get_llm
from utils.resilience import resilient_invoke

logger = logging.getLogger(__name__)


@lru_cache
def _get_condenser():
    # Short, deterministic rewrite — a tiny token budget keeps latency/cost negligible.
    return get_llm(temperature=0, max_tokens=64)


def condense_query(state):
    question = state["question"]
    settings = get_settings()

    messages = state.get("messages") or []
    summary = state.get("summary", "")

    # Pass-through when disabled or when there is no prior context to condense against
    # (first turn) — no LLM call, so first-turn latency is unchanged.
    if not settings.query_rewrite_enabled or (not messages and not summary):
        return {"search_query": question}

    recent = messages[-6:]
    history = "\n".join(f"{'User' if isinstance(m, HumanMessage) else 'AI'}: {m.content}" for m in recent)
    prompt = build_condense_prompt(summary=summary, history=history, question=question)

    try:
        response = resilient_invoke(_get_condenser().invoke, prompt)
        rewritten = (getattr(response, "content", "") or "").strip()
    except Exception as e:  # pragma: no cover - defensive: never fail a turn on rewrite
        logger.warning("Query condense failed (%s); falling back to raw question", e)
        rewritten = ""

    search_query = rewritten or question
    if rewritten and rewritten != question:
        logger.info("Condensed query: %r → %r", question, search_query)
    return {"search_query": search_query}
