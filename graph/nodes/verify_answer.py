"""Groundedness / faithfulness verification (#2).

After generation, check whether the answer is actually supported by the retrieved chunks
and expose a real ``grounded`` signal (``supported`` | ``partial`` | ``unsupported``) plus
``grounded_score``. The web confidence badge can then reflect *answer support*, not just
retrieval similarity.

In **strict** mode an ``unsupported`` verdict converts a subtle hallucination into the
canonical "Not in the knowledge base" refusal (and clears sources). In ``open``/``learning``
the answer is kept; only the signal is surfaced so the UI can downgrade confidence.

Two tiers, config-selectable:
- ``heuristic`` (default, no extra LLM call) — content-word overlap of each answer sentence
  against the retrieved context.
- ``llm`` — a single JSON-judge call (wrapped in the resilience layer, #14).
"""

import json
import logging
import re
from functools import lru_cache

from langchain_core.messages import AIMessage

from config import get_settings
from prompts.verify import build_verify_prompt
from utils.llm_adapter import get_llm
from utils.resilience import resilient_invoke

logger = logging.getLogger(__name__)

# A sentence counts as "supported" when at least this fraction of its content words appear
# in the retrieved context (lenient enough for paraphrase, strict enough to catch invention).
_SUPPORT_RATIO = 0.6
_WORD = re.compile(r"[a-z0-9]+")
_SENTENCE_SPLIT = re.compile(r"[.!?\n]+")
# Tiny stopword set + short-token filter so overlap reflects substantive content, not glue.
_STOPWORDS = frozenset(
    "the a an of to in on for and or is are was were be been being it its this that these those "
    "you your we our they their i he she as at by with from will would can could may might do does "
    "did have has had not no yes but if then so than there here about into over under more most".split()
)


@lru_cache
def _get_judge():
    return get_llm(temperature=0, max_tokens=256)


def _content_tokens(text: str) -> set[str]:
    return {t for t in _WORD.findall((text or "").lower()) if len(t) >= 3 and t not in _STOPWORDS}


def _heuristic_score(answer: str, docs: str) -> float:
    """Fraction of answer sentences whose content words are largely present in ``docs``."""
    doc_tokens = _content_tokens(docs)
    if not doc_tokens:
        return 0.0
    supported = 0
    counted = 0
    for sentence in _SENTENCE_SPLIT.split(answer or ""):
        stoks = _content_tokens(sentence)
        if not stoks:
            continue
        counted += 1
        overlap = len(stoks & doc_tokens) / len(stoks)
        if overlap >= _SUPPORT_RATIO:
            supported += 1
    if counted == 0:
        return 0.0
    return supported / counted


def _llm_verdict(answer: str, docs: str) -> float:
    """Return 1.0 when the LLM judge says grounded, else 0.0. Falls back to 1.0 on parse error."""
    prompt = build_verify_prompt(answer=answer, docs=docs)
    try:
        response = resilient_invoke(_get_judge().invoke, prompt)
        raw = (getattr(response, "content", "") or "").strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        data = json.loads(match.group(0) if match else raw)
        return 1.0 if bool(data.get("grounded")) else 0.0
    except Exception as e:  # pragma: no cover - defensive: never fail a turn on the judge
        logger.warning("LLM groundedness judge failed (%s); treating as supported", e)
        return 1.0


def _bucket(score: float, min_score: float) -> str:
    if score >= min_score:
        return "supported"
    if score <= 0.0:
        return "unsupported"
    return "partial"


def verify_answer(state):
    settings = get_settings()
    docs = state.get("docs", "") or ""
    answer = state.get("last_answer", "") or ""

    # Only meaningful when we have retrieved context to verify against.
    if not settings.groundedness_enabled or not docs.strip() or not answer.strip():
        return {}

    if settings.groundedness_mode == "llm":
        score = _llm_verdict(answer, docs)
    else:
        score = _heuristic_score(answer, docs)

    verdict = _bucket(score, settings.groundedness_min_score)
    grounded_score = round(score, 4)
    result: dict = {"grounded": verdict, "grounded_score": grounded_score}

    chat_mode = state.get("chat_mode", "strict")
    if chat_mode == "strict" and verdict == "unsupported" and settings.strict_refuse_on_ungrounded:
        refusal = f"I don't have information about that in our knowledge base. {settings.escalation_message}"
        logger.info("Strict groundedness gate: refusing ungrounded answer (score=%.2f)", grounded_score)
        result["last_answer"] = refusal
        result["sources"] = []
        # Rewrite the stored answer so memory/self-ingest see the refusal, not the hallucination.
        messages = list(state.get("messages") or [])
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], AIMessage):
                messages[i] = AIMessage(content=refusal)
                break
        result["messages"] = messages

    return result
