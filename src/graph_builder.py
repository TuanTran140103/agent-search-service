from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from src.agent.nodes.agent import agent_node
from src.agent.nodes.human_approval import human_approval_node
from src.agent.tools.search_tool import SEARCH_TOOLS
from src.models.agent import AgentState

_checkpointer = MemorySaver()


def get_checkpointer() -> MemorySaver:
    return _checkpointer


def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("agent", agent_node)
    workflow.add_node("human_approval", human_approval_node)
    workflow.add_node("tool_node", ToolNode(SEARCH_TOOLS))

    workflow.add_edge(START, "agent")
    workflow.add_edge("tool_node", "agent")

    return workflow.compile(checkpointer=_checkpointer)


def create_agent(name: str, description: str | None = None) -> "LangGraphAgent":
    from ag_ui_langgraph import LangGraphAgent

    graph = build_graph()
    return LangGraphAgent(name=name, description=description, graph=graph)


graph = build_graph()

__all__ = ["graph", "build_graph", "create_agent", "get_checkpointer"]
