from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, AsyncIterator

import redis.asyncio as aioredis

from ag_ui.core import BaseEvent, EventType, RunAgentInput

from src.queue.protocol import MessageQueue

logger = logging.getLogger(__name__)

STREAM_KEY = "agent:requests"
CONSUMER_GROUP = "agent-workers"
EVENT_CHANNEL_PREFIX = "agent:events:"


class RedisStreamQueue(MessageQueue):
    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._redis: aioredis.Redis | None = None
        self._agents: dict[str, Any] = {}
        self._worker_task: asyncio.Task | None = None
        self._running = False

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._redis_url, decode_responses=True
            )
        return self._redis

    async def publish(self, agent_name: str, input: RunAgentInput) -> str:
        r = await self._get_redis()
        run_id = input.run_id or str(uuid.uuid4())

        await r.xadd(
            STREAM_KEY,
            {
                "agent_name": agent_name,
                "run_id": run_id,
                "payload": input.model_dump_json(exclude_none=True),
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

    async def start_worker(self, agents: dict[str, Any] | None = None) -> None:
        if agents:
            self._agents = agents
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("RedisStreamQueue worker started")

    async def _worker_loop(self) -> None:
        r = await self._get_redis()

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
                logger.exception("RedisStreamQueue worker error")
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
        channel = f"{EVENT_CHANNEL_PREFIX}{run_id}"

        logger.info("Worker processing run_id=%s agent=%s", run_id, agent_name)

        async for event in agent.run(payload):
            await r.publish(
                channel, event.model_dump_json(exclude_none=True)
            )

        await r.xack(STREAM_KEY, CONSUMER_GROUP, entry_id)
        logger.info("Worker completed run_id=%s", run_id)

    async def shutdown(self) -> None:
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        if self._redis:
            await self._redis.close()
        logger.info("RedisStreamQueue worker stopped")
