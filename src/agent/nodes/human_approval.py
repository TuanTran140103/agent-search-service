from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command, interrupt


async def human_approval_node(state: dict) -> Command[Literal["tool_node", "agent"]]:
    messages = state.get("messages", [])
    if not messages:
        return Command(goto="agent")

    last_msg = messages[-1]
    if not isinstance(last_msg, AIMessage) or not last_msg.tool_calls:
        return Command(goto="agent")

    tool_calls = [
        {"name": tc["name"], "args": tc["args"]}
        for tc in last_msg.tool_calls
    ]

    decision = interrupt({
        "type": "tool_approval",
        "question": "Approve the following tool calls?",
        "tool_calls": tool_calls,
    })

    action = "approve"
    if isinstance(decision, dict):
        action = decision.get("action", "approve")

    if action == "reject":
        reject_msgs = []
        for tc in last_msg.tool_calls:
            reject_msgs.append(
                ToolMessage(
                    content=f"User rejected tool call: {tc['name']}",
                    tool_call_id=tc["id"],
                )
            )
        return Command(
            goto="agent",
            update={"messages": reject_msgs},
        )

    return Command(goto="tool_node")
