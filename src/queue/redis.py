from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import AsyncIterator

import redis.asyncio as aioredis
from langchain_core.runnables import RunnableConfig, ensure_config

from ag_ui.core import BaseEvent, EventType, RunAgentInput
from ag_ui_langgraph import LangGraphAgent

from src.queue.protocol import MessageQueue, Worker

logger = logging.getLogger(__name__)

STREAM_KEY = "agent:requests"
CONSUMER_GROUP = "agent-workers"
EVENT_CHANNEL_PREFIX = "agent:events:"


class RedisStreamQueue(MessageQueue):
    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._redis_url, decode_responses=True
            )
        return self._redis

    async def publish(self, agent_name: str, input: RunAgentInput) -> str:
        r = await self._get_redis()
        run_id = input.run_id or str(uuid.uuid4())
        input_with_id = input.model_copy(update={"run_id": run_id})

        await r.xadd(
            STREAM_KEY,
            {
                "agent_name": agent_name,
                "run_id": run_id,
                "payload": input_with_id.model_dump_json(),
            },
            maxlen=10000,
        )
        return run_id

    async def subscribe(self, run_id: str) -> AsyncIterator[BaseEvent]:
        r = await self._get_redis()
        pubsub = r.pubsub()
        channel = f"{EVENT_CHANNEL_PREFIX}{run_id}"
        await pubsub.subscribe(channel)

        try:
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                data = json.loads(message["data"])
                event = BaseEvent.model_validate(data)
                yield event
                if event.type in (EventType.RUN_FINISHED, EventType.RUN_ERROR):
                    break
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    async def shutdown(self) -> None:
        if self._redis:
            await self._redis.close()
        logger.info("RedisStreamQueue shut down")


class RedisStreamWorker(Worker):
    def __init__(self, queue: RedisStreamQueue):
        self._queue = queue
        self._agents: dict[str, LangGraphAgent] = {}
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self, agents: dict[str, LangGraphAgent]) -> None:
        self._agents = agents
        self._running = True
        self._task = asyncio.create_task(self._worker_loop())
        logger.info("RedisStreamWorker started")

    async def _worker_loop(self) -> None:
        r = await self._queue._get_redis()

        try:
            await r.xgroup_create(STREAM_KEY, CONSUMER_GROUP, mkstream=True)
        except aioredis.ResponseError:
            pass

        consumer_name = f"worker-{uuid.uuid4().hex[:8]}"

        while self._running:
            try:
                results = await r.xreadgroup(
                    CONSUMER_GROUP,
                    consumer_name,
                    {STREAM_KEY: ">"},
                    count=1,
                    block=5000,
                )

                if not results:
                    continue

                for stream_key, entries in results:
                    for entry_id, data in entries:
                        await self._process_entry(r, entry_id, dict(data))

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("RedisStreamWorker error")
                await asyncio.sleep(1)

    async def _process_entry(
        self, r: aioredis.Redis, entry_id: str, data: dict
    ) -> None:
        decoded = {}
        for k, v in data.items():
            key = k.decode() if isinstance(k, bytes) else k
            val = v.decode() if isinstance(v, bytes) else v
            decoded[key] = val

        run_id = decoded.get("run_id", "")
        agent_name = decoded.get("agent_name", "")
        payload_raw = decoded.get("payload", "{}")
        payload = RunAgentInput.model_validate_json(payload_raw)

        if agent_name not in self._agents:
            logger.error("Unknown agent: %s", agent_name)
            await r.xack(STREAM_KEY, CONSUMER_GROUP, entry_id)
            return

        agent = self._agents[agent_name].clone()

        # Inject dataset_ids from forwarded_props into agent config so tools
        # can access them via ToolRuntime.config["configurable"]["dataset_ids"]
        forwarded = payload.forwarded_props or {}
        if isinstance(forwarded, dict):
            ds_ids = forwarded.get("dataset_ids")
            if ds_ids is not None:
                cfg: RunnableConfig = ensure_config(
                    dict(agent.config) if agent.config else {}
                )
                cfg.setdefault("configurable", {})["dataset_ids"] = ds_ids
                agent.config = cfg

        channel = f"{EVENT_CHANNEL_PREFIX}{run_id}"

        logger.info("Worker processing run_id=%s agent=%s", run_id, agent_name)

        # Use checkpoint as source of truth, only accept truly new user messages from client
        from ag_ui_langgraph.utils import langchain_messages_to_agui
        from langchain_core.messages.modifier import RemoveMessage

        state = await agent.graph.aget_state({"configurable": {"thread_id": payload.thread_id}})
        checkpoint_raw = list(state.values.get("messages", [])) if state.values else []
        checkpoint_msgs = [m for m in checkpoint_raw if not isinstance(m, RemoveMessage)]
        checkpoint_agui = langchain_messages_to_agui(checkpoint_msgs)
        checkpoint_agui_ids = {m.id for m in checkpoint_agui if m.id}

        new_user_msgs = [m for m in (payload.messages or [])
                         if getattr(m, 'role', None) == 'user'
                         and getattr(m, 'id', None)
                         and m.id not in checkpoint_agui_ids]

        if new_user_msgs:
            payload.messages = [*checkpoint_agui, *new_user_msgs]
        else:
            payload.messages = checkpoint_agui

        async for event in agent.run(payload):
            if event.type == EventType.TEXT_MESSAGE_CONTENT or event.type == EventType.TOOL_CALL_ARGS:
                logger.info("[LLM] %s", event.model_dump_json(exclude_none=True))
            await r.publish(
                channel, event.model_dump_json(exclude_none=True)
            )

        await r.xack(STREAM_KEY, CONSUMER_GROUP, entry_id)
        logger.info("Worker completed run_id=%s", run_id)

    async def shutdown(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("RedisStreamWorker stopped")

