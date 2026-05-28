from langchain_core.messages import BaseMessage
from typing_extensions import TypedDict


class State(TypedDict):
    user_id: str
    question: str
    messages: list[BaseMessage]
    docs: str
    summary: str
    sources: list[str]
