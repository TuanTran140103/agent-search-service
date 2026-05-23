from __future__ import annotations

from src.graph_builder import build_deep_agent, create_agent_inst

# Referenced by ``langgraph.json`` as ``./src/agent/graph.py:graph``.
# When running outside LangSmith Cloud the graph is built by the DI
# container at startup; this module re-exports the builder functions
# for platform compatibility.

__all__ = ["build_deep_agent", "create_agent_inst"]
