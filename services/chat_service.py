from functools import lru_cache

from config import get_settings
from graph.builder import build_graph

_graph = lru_cache(maxsize=1)(build_graph)


def conversation(user_id: str, q: str):
    chat_mode = get_settings().chat_mode.lower()
    result = _graph().invoke(
        {
            "user_id": user_id,
            "question": q,
            "chat_mode": chat_mode,
        }
    )

    return {
        "answer": result["messages"][-1].content,
        "sources": result.get("sources", []),
        "self_ingested": result.get("self_ingested", False),
    }
