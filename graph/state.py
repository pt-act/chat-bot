from typing import List
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage


class State(TypedDict):
    user_id: str
    question: str
    messages: list[BaseMessage]
    docs: str
    summary: str
    sources: List[str]