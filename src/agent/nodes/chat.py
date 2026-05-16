from __future__ import annotations

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import MessagesState
from langgraph.types import Command
from typing import Literal

from src.services.llm_service import llm_service


async def chat_node(
    state: MessagesState, config: RunnableConfig
) -> Command[Literal["__end__"]]:
    model = llm_service.get_chat_model(
        model=config["configurable"].get("model_name"),
    )

    system_prompt = """You are a helpful AI assistant.
You can search and retrieve information from documents to answer user questions.
Use the tools available to you when needed."""

    response = await model.ainvoke(
        [SystemMessage(content=system_prompt), *state["messages"]], config
    )

    return Command(goto="__end__", update={"messages": [response]})
