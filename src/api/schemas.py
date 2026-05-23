from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class UpdateStateRequest(BaseModel):
    messages: list[dict] = []


class ForkThreadRequest(BaseModel):
    source_checkpoint_id: str | None = None
    new_thread_id: str | None = None


class UpdateStateResponse(BaseModel):
    thread_id: str
    checkpoint_id: str | None = None
    messages: list[dict[str, Any]]
