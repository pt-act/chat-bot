import logging
import re
from functools import lru_cache

from langchain_core.messages import AIMessage, HumanMessage

from prompts.answer import build_answer_prompt
from utils.llm_adapter import get_llm

logger = logging.getLogger(__name__)


@lru_cache
def _get_chat():
    return get_llm(temperature=0, max_tokens=512)


def _response_language(question: str) -> str:
    return "Arabic" if re.search(r"[؀-ۿ]", question) else "English"


# Per-request language overrides ("auto" falls back to detection).
_LANG_LABELS = {"en": "English", "ar": "Arabic"}


def _resolve_language(state, question: str) -> str:
    requested = (state.get("lang") or "auto").lower()
    return _LANG_LABELS.get(requested, _response_language(question))


def build_chat_prompt(state) -> tuple[str, str]:
    """Build the answer prompt and resolved language for a state.

    Shared by the synchronous node (generate_answer) and the streaming path
    (services.chat_service.stream_conversation) so prompt construction stays DRY.
    """
    summary = state.get("summary", "")
    messages = state.get("messages") or []
    docs = state.get("docs", "")
    question = state["question"]
    lang = _resolve_language(state, question)
    chat_mode = state.get("chat_mode", "strict")

    recent = messages[-6:]
    history = "\n".join(f"{'User' if isinstance(m, HumanMessage) else 'AI'}: {m.content}" for m in recent)

    prompt = build_answer_prompt(
        summary=summary,
        history=history,
        docs=docs,
        question=question,
        lang=lang,
        chat_mode=chat_mode,
    )
    return prompt, lang


def generate_answer(state):
    messages = state.get("messages") or []
    question = state["question"]
    chat_mode = state.get("chat_mode", "strict")

    prompt, lang = build_chat_prompt(state)

    response = _get_chat().invoke(prompt)
    logger.info("Generated answer for user %s (lang=%s, mode=%s)", state.get("user_id"), lang, chat_mode)

    return {
        "messages": messages
        + [
            HumanMessage(content=question),
            AIMessage(content=response.content),
        ],
        "last_answer": response.content,
        "lang": lang,  # resolved label, surfaced in response meta
    }
