from __future__ import annotations

import abc
from typing import AsyncIterator

from ag_ui.core import BaseEvent, RunAgentInput
from ag_ui_langgraph import LangGraphAgent


class MessageQueue(abc.ABC):
    @abc.abstractmethod
    async def publish(self, agent_name: str, input: RunAgentInput) -> str:
        ...

    @abc.abstractmethod
    async def subscribe(self, run_id: str) -> AsyncIterator[BaseEvent]:
        ...

    @abc.abstractmethod
    async def shutdown(self) -> None:
        ...


class Worker(abc.ABC):
    @abc.abstractmethod
    async def start(self, agents: dict[str, LangGraphAgent]) -> None:
        ...

    @abc.abstractmethod
    async def shutdown(self) -> None:
        ...
