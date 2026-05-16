from __future__ import annotations

from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel

from src.core.config import settings


class LLMService:
    def __init__(self):
        self.api_key = settings.llm_api_key
        self.model = settings.llm_model
        self.base_url = settings.llm_base_url
        self.temperature = settings.llm_temperature
        self.max_tokens = settings.llm_max_tokens

    def get_chat_model(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> BaseChatModel:
        return ChatOpenAI(
            model=model or self.model,
            api_key=api_key or self.api_key,
            base_url=base_url or self.base_url,
            temperature=temperature if temperature is not None else self.temperature,
            max_tokens=max_tokens or self.max_tokens,
        )

    def get_supervisor_model(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> BaseChatModel:
        return ChatOpenAI(
            model=model or settings.supervisor_model or self.model,
            api_key=api_key or settings.supervisor_api_key or self.api_key,
            base_url=base_url or settings.supervisor_base_url or self.base_url,
            temperature=0,
        )


llm_service = LLMService()
