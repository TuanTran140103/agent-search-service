from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AnyMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from src.core.config import settings
from src.services.llm_service import llm_factory


def create_subagent_model(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.3,
) -> BaseChatModel:
    return llm_factory.create(
        provider=provider or settings.llm_provider,
        model=model or settings.llm_model,
        temperature=temperature,
    )


def filter_tools(tools: Sequence[BaseTool], names: set[str]) -> list[BaseTool]:
    return [t for t in tools if t.name in names]


def _has_tool_calls(messages: list[AnyMessage]) -> bool:
    last = messages[-1]
    return bool(getattr(last, "tool_calls", None))


def build_subagent_workflow(
    model: BaseChatModel,
    research_tools: list[BaseTool],
    research_prompt: str,
    synthesis_prompt: str,
) -> CompiledStateGraph:
    """Build a two-phase workflow: Research → Synthesis.

    - **Research phase**: LLM can call ``research_tools`` to gather information.
      Transitions to synthesis automatically when the LLM stops calling tools.
    - **Synthesis phase**: LLM-only, no tools available. Produces the final answer.
    """

    def call_research(state: MessagesState) -> dict:
        msgs = list(state["messages"])
        if not any(isinstance(m, SystemMessage) for m in msgs):
            msgs.insert(0, SystemMessage(content=research_prompt))
        return {"messages": [model.invoke(msgs)]}

    def call_synthesis(state: MessagesState) -> dict:
        msgs = list(state["messages"])
        if not any(isinstance(m, SystemMessage) for m in msgs):
            msgs.insert(0, SystemMessage(content=synthesis_prompt))
        return {"messages": [model.invoke(msgs)]}

    def route_research(state: MessagesState) -> str:
        return "tools" if _has_tool_calls(state["messages"]) else "synthesis"

    workflow = StateGraph(MessagesState)
    workflow.add_node("research", call_research)
    workflow.add_node("tools", ToolNode(research_tools))
    workflow.add_node("synthesis", call_synthesis)

    workflow.add_edge(START, "research")
    workflow.add_conditional_edges(
        "research",
        route_research,
        {"tools": "tools", "synthesis": "synthesis"},
    )
    workflow.add_edge("tools", "research")
    workflow.add_edge("synthesis", END)

    return workflow.compile()
