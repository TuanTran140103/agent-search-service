from __future__ import annotations

from typing import Optional

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_nvidia_ai_endpoints import ChatNVIDIA

from src.core.config import settings


class LLMFactory:
    """Factory that creates LLM instances for any supported provider.

    Each provider method accepts an optional ``base_url`` so you can route
    through proxies, gateways, or local OpenAI-compatible servers.
    """

    PROVIDER_MAP = {
        "openai": "create_openai",
        "anthropic": "create_anthropic",
        "google_genai": "create_google_genai",
        "nvidia": "create_nvidia",
    }

    # ── Provider helpers ─────────────────────────────────────────────────

    @staticmethod
    def create_openai(
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> ChatOpenAI:
        return ChatOpenAI(
            model=model,
            api_key=api_key or settings.llm_api_key,
            base_url=base_url or settings.llm_base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=True,
            stream_usage=True,
            **kwargs,
        )

    @staticmethod
    def create_anthropic(
        model: str = "claude-sonnet-4-6",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> ChatAnthropic:
        return ChatAnthropic(
            model=model,
            api_key=api_key or settings.anthropic_api_key or settings.llm_api_key,
            base_url=base_url or settings.anthropic_base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=True,
            **kwargs,
        )

    @staticmethod
    def create_google_genai(
        model: str = "gemini-2.0-flash",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> ChatGoogleGenerativeAI:
        return ChatGoogleGenerativeAI(
            model=model,
            api_key=api_key or settings.google_api_key or settings.llm_api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=True,
            **kwargs,
        )

    @staticmethod
    def create_nvidia(
        model: str = "meta/llama-3.1-70b-instruct",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> ChatNVIDIA:
        return ChatNVIDIA(
            model=model,
            api_key=api_key or settings.nvidia_api_key or settings.llm_api_key,
            base_url=base_url or settings.nvidia_base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    # ── Generic dispatcher ───────────────────────────────────────────────

    def create(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> BaseChatModel:
        provider = (provider or settings.llm_provider).lower()
        model = model or settings.llm_model
        temperature = temperature if temperature is not None else settings.llm_temperature
        max_tokens = max_tokens or settings.llm_max_tokens

        method_name = self.PROVIDER_MAP.get(provider)
        if method_name is None:
            raise ValueError(
                f"Unknown provider '{provider}'. "
                f"Supported: {', '.join(self.PROVIDER_MAP)}"
            )

        method = getattr(self, method_name)
        return method(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

    # ── DeepAgents shortcut ──────────────────────────────────────────────

    def create_deepagent_model(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs,
    ) -> BaseChatModel:
        """Convenience method for creating the model used by DeepAgents."""
        return self.create(
            provider=provider,
            model=model,
            **kwargs,
        )


llm_factory = LLMFactory()
