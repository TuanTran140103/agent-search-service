from __future__ import annotations

from langgraph.graph import MessagesState


class AgentState(MessagesState):
    instructions: str = ""
