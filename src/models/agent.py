from __future__ import annotations

# AgentState is now managed internally by DeepAgents.
# This module is kept as a compatibility shim in case other
# parts of the codebase import from here.
from langgraph.graph import MessagesState as AgentState

__all__ = ["AgentState"]
