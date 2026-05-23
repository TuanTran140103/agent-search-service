from __future__ import annotations

from ag_ui_langgraph import LangGraphAgent
from dependency_injector.wiring import Provide, inject

from src.container import ApplicationContainer
from src.core.config import Settings


@inject
async def build_agent_registry(
    settings: Settings = Provide[ApplicationContainer.settings],
    agent: LangGraphAgent = Provide[ApplicationContainer.agent],
) -> dict[str, LangGraphAgent]:
    return {settings.agent_name: agent}
