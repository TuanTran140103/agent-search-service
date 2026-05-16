from __future__ import annotations

import abc
from typing import AsyncIterator

from ag_ui.core import BaseEvent, RunAgentInput


class MessageQueue(abc.ABC):
    @abc.abstractmethod
    async def publish(self, agent_name: str, input: RunAgentInput) -> str:
        ...

    @abc.abstractmethod
    async def subscribe(self, run_id: str) -> AsyncIterator[BaseEvent]:
        ...

    @abc.abstractmethod
    async def start_worker(self, agents: dict[str, object]) -> None:
        ...

    @abc.abstractmethod
    async def shutdown(self) -> None:
        ...
