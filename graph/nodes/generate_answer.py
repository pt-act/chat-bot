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


def generate_answer(state):
    summary = state.get("summary", "")
    messages = state.get("messages") or []
    docs = state.get("docs", "")
    question = state["question"]
    lang = _response_language(question)
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

    response = _get_chat().invoke(prompt)
    logger.info("Generated answer for user %s (lang=%s, mode=%s)", state.get("user_id"), lang, chat_mode)

    return {
        "messages": messages
        + [
            HumanMessage(content=question),
            AIMessage(content=response.content),
        ],
        "last_answer": response.content,
    }
