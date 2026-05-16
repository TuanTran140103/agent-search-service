from __future__ import annotations
from typing import Literal

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from src.agent.tools.search_tool import SEARCH_TOOLS
from src.core.log import get_logger
from src.services.llm_service import llm_service

logger = get_logger("agent")

SYSTEM_PROMPT = """You are a helpful AI assistant with document search capabilities.

You can:
- Chat naturally about any topic
- Search for information in documents when the user needs it

When the user asks to search, find, or retrieve information from documents, use the available search tools. For general conversation, just respond directly.

Available tools:
- search_by_name: Find documents by filename (fuzzy search)
- vector_search: Semantic search across document content
- read_document: Read full content or summary of a document
- list_dataset_documents: Browse documents in a dataset"""


async def agent_node(
    state: dict, config: RunnableConfig
) -> Command[Literal["human_approval", "__end__"]]:
    configurable = config.get("configurable", {})
    model = llm_service.get_chat_model(
        model=configurable.get("model_name"),
        temperature=configurable.get("temperature"),
    )
    model_with_tools = model.bind_tools(SEARCH_TOOLS, parallel_tool_calls=False)

    instructions = state.get("instructions", "")
    system_prompt = SYSTEM_PROMPT
    if instructions:
        system_prompt += f"\n\nInstructions: {instructions}"

    messages = state.get("messages", [])
    response = await model_with_tools.ainvoke(
        [SystemMessage(content=system_prompt), *messages],
        config,
    )

    has_tc = bool(response.tool_calls)
    if has_tc:
        logger.info(
            "agent_tool_call",
            tool=response.tool_calls[0]["name"],
            args=response.tool_calls[0]["args"],
        )
    else:
        logger.info(
            "agent_response",
            content=response.content,
        )

    if has_tc:
        return Command(
            goto="human_approval",
            update={"messages": [response]},
        )

    return Command(
        goto="__end__",
        update={"messages": [response]},
    )
