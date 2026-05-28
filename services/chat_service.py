from langchain_core.messages import HumanMessage
from functools import lru_cache

from graph.builder import build_graph

_graph = lru_cache(maxsize=1)(build_graph)


def conversation(user_id: str, q: str):
    result = _graph().invoke({
        "user_id": user_id,
        "question": q,
    })

    return {
        "answer": result["messages"][-1].content,
        "sources": result.get("sources", []),
    }