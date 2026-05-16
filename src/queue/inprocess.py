from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator

from ag_ui.core import (
    BaseEvent,
    EventType,
    RunAgentInput,
    RunErrorEvent,
)

from src.queue.protocol import MessageQueue

logger = logging.getLogger(__name__)


class InProcessQueue(MessageQueue):
    def __init__(self, maxsize: int = 200):
        self._request_queue: asyncio.Queue[tuple[str, RunAgentInput]] = asyncio.Queue(
            maxsize=maxsize
        )
        self._channels: dict[str, asyncio.Queue[BaseEvent]] = {}
        self._agents: dict[str, Any] = {}
        self._worker_task: asyncio.Task | None = None
        self._running = False

    async def publish(self, agent_name: str, input: RunAgentInput) -> str:
        run_id = input.run_id
        if not run_id:
            import uuid

            run_id = str(uuid.uuid4())

        self._channels[run_id] = asyncio.Queue()
        await self._request_queue.put((agent_name, input))
        return run_id

    async def subscribe(self, run_id: str) -> AsyncIterator[BaseEvent]:
        channel = self._channels.get(run_id)
        if channel is None:
            raise ValueError(f"Unknown run_id: {run_id}")

        try:
            while True:
                event = await asyncio.wait_for(channel.get(), timeout=300)
                yield event
                if event.type in (EventType.RUN_FINISHED, EventType.RUN_ERROR):
                    break
        except asyncio.TimeoutError:
            logger.warning("Subscribe timeout for run_id=%s", run_id)
            yield RunErrorEvent(
                type=EventType.RUN_ERROR,
                message="Request timed out after 300s",
            )
        finally:
            self._channels.pop(run_id, None)

    async def start_worker(self, agents: dict[str, Any]) -> None:
        self._agents = agents
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info(
            "InProcessQueue worker started with %d agents", len(agents)
        )

    async def _worker_loop(self) -> None:
        while self._running:
            try:
                agent_name, input_data = await self._request_queue.get()
                run_id = input_data.run_id
                agent = self._agents[agent_name].clone()
                channel = self._channels.get(run_id)
                if channel is None:
                    continue

                try:
                    async for event in agent.run(input_data):
                        await channel.put(event)
                except Exception as exc:
                    logger.exception(
                        "Worker error for run_id=%s agent=%s", run_id, agent_name
                    )
                    error_channel = self._channels.get(run_id)
                    if error_channel:
                        await error_channel.put(
                            RunErrorEvent(
                                type=EventType.RUN_ERROR,
                                message=str(exc),
                            )
                        )
                else:
                    await _persist_thread_messages(input_data, agent.graph)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("InProcessQueue worker fatal error")

    async def shutdown(self) -> None:
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("InProcessQueue worker stopped")


async def _persist_thread_messages(
    input_data: RunAgentInput, graph: Any
) -> None:
    if not input_data.thread_id:
        return

    config = {"configurable": {"thread_id": input_data.thread_id}}
    try:
        state = await graph.aget_state(config)
        if state.values and state.values.get("messages"):
            msg_count = len(state.values["messages"])
            logger.info(
                "thread_state_verified",
                thread_id=input_data.thread_id,
                message_count=msg_count,
            )
            return

        logger.warning(
            "thread_state_empty_after_run",
            thread_id=input_data.thread_id,
        )
        if not input_data.messages:
            return

        from ag_ui_langgraph.utils import agui_messages_to_langchain

        langchain_msgs = agui_messages_to_langchain(input_data.messages)
        await graph.aupdate_state(
            config,
            {"messages": langchain_msgs},
        )
        logger.info(
            "thread_state_recovered",
            thread_id=input_data.thread_id,
            message_count=len(langchain_msgs),
        )
    except Exception:
        logger.exception(
            "thread_state_persist_error",
            thread_id=input_data.thread_id,
        )
