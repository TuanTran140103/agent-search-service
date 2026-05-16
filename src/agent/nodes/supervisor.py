from __future__ import annotations

import json
from typing import Literal

from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END
from langgraph.types import Command
from pydantic import BaseModel, Field

from src.core.log import get_logger
from src.services.llm_service import llm_service

logger = get_logger("supervisor")


class SupervisorDecision(BaseModel):
    next: Literal["search_agent", "chat_agent", "FINISH"] = Field(
        description="Next agent to route to"
    )
    reasoning: str = Field(
        description="Why this decision was made based on the conversation"
    )
    instructions: str = Field(
        default="",
        description="Specific instructions for the selected agent on what to do",
    )


SUPERVISOR_SYSTEM_PROMPT = """You are a routing supervisor for a multi-agent system.
Analyze the conversation and decide which agent should handle the next step.

Available agents:
- "search_agent": Route here when the user wants to search, find, or retrieve information from documents.
- "chat_agent": Route here for general conversation, greetings, small talk, or questions that don't involve documents.
- "FINISH": Choose this when the user's request has been fully resolved and no further action is needed.

Rules:
- If the last message is from an agent that already provided a complete response, choose FINISH.
- If the user is asking a new question that requires document search, route to search_agent.
- For general chat that doesn't need document access, route to chat_agent.
- Never route to search_agent unless the user explicitly needs document information.

You MUST output your decision as a JSON object in this exact format:
{"next": "search_agent", "reasoning": "...", "instructions": "..."}"""


def _parse_decision(response) -> SupervisorDecision:
    if response.tool_calls:
        try:
            args = response.tool_calls[0]["args"]
            return SupervisorDecision(**args)
        except Exception:
            pass

    content = response.content.strip()
    content = content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(content)
        return SupervisorDecision(**data)
    except Exception:
        pass

    return SupervisorDecision(next="FINISH", reasoning="Could not parse decision", instructions="")


async def supervisor_node(
    state: dict, config: RunnableConfig
) -> Command[Literal["search_agent", "chat_agent", "__end__"]]:
    configurable = config.get("configurable", {})
    model = llm_service.get_supervisor_model(
        model=configurable.get("supervisor_model"),
    )

    model_with_tools = model.bind_tools([SupervisorDecision])

    messages = state.get("messages", [])
    msg_count = len(messages)
    last_msg = messages[-1] if messages else None

    logger.info(
        "supervisor_enter",
        msg_count=msg_count,
        last_msg_type=type(last_msg).__name__ if last_msg else None,
        last_msg_content=str(last_msg.content)[:150] if last_msg else None,
    )

    response = await model_with_tools.ainvoke(
        [SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT), *messages],
    )

    decision = _parse_decision(response)

    logger.info(
        "supervisor_decision",
        decision_next=decision.next,
        decision_reasoning=decision.reasoning,
        has_tool_calls=bool(response.tool_calls),
        response_preview=str(response.content)[:150] if not response.tool_calls else str(response.tool_calls[0]["args"])[:150],
    )

    goto = END if decision.next == "FINISH" else decision.next
    return Command(
        goto=goto,
        update={"instructions": decision.instructions},
    )
