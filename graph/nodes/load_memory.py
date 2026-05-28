import json
import logging

from langchain_core.messages import AIMessage, HumanMessage

from db.redis_client import get_redis

logger = logging.getLogger(__name__)


def load_memory(state):
    redis = get_redis()
    user_id = state["user_id"]
    data = redis.get(user_id)

    if not data:
        return {"messages": [], "summary": ""}

    data = json.loads(data)
    messages = []
    for m in data.get("messages", []):
        if m["role"] == "user":
            messages.append(HumanMessage(content=m["content"]))
        else:
            messages.append(AIMessage(content=m["content"]))

    logger.info("Loaded memory for user %s (%d messages)", user_id, len(messages))
    return {"messages": messages, "summary": data.get("summary", "")}