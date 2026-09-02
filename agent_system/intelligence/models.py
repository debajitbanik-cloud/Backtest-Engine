"""
Model Provider Abstraction — DeepSeek, OpenAI-compatible, and other providers.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx


@dataclass
class ModelConfig:
    """Configuration for a model provider."""
    provider: str  # "deepseek", "openai", "anthropic", "ollama", "litellm"
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.1
    max_tokens: int = 4096
    timeout: int = 60
    extra_params: Dict[str, Any] = None


@dataclass
class Message:
    """Chat message."""
    role: str  # "system", "user", "assistant", "tool"
    content: str
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None


@dataclass
class CompletionResponse:
    """Model completion response."""
    content: str
    tool_calls: Optional[List[Dict]] = None
    finish_reason: str = "stop"
    usage: Dict[str, int] = None


class ModelProvider(ABC):
    """Abstract base for model providers."""

    def __init__(self, config: ModelConfig):
        self.config = config

    @abstractmethod
    async def complete(
        self,
        messages: List[Message],
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
        stream: bool = False,
    ) -> CompletionResponse:
        """Generate a completion."""
        pass

    @abstractmethod
    async def stream_complete(
        self,
        messages: List[Message],
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Stream completion tokens."""
        pass


class OpenAICompatibleProvider(ModelProvider):
    """OpenAI-compatible API provider (works with DeepSeek, OpenAI, etc.)."""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self.base_url = config.base_url or "https://api.openai.com/v1"
        self.api_key = config.api_key
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"} if self.api_key else {},
            timeout=config.timeout,
        )

    async def complete(
        self,
        messages: List[Message],
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
        stream: bool = False,
    ) -> CompletionResponse:
        payload = {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice
        if self.config.extra_params:
            payload.update(self.config.extra_params)

        response = await self.client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        return CompletionResponse(
            content=choice["message"].get("content", ""),
            tool_calls=choice["message"].get("tool_calls"),
            finish_reason=choice.get("finish_reason", "stop"),
            usage=data.get("usage"),
        )

    async def stream_complete(
        self,
        messages: List[Message],
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice

        async with self.client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    import json
                    chunk = json.loads(data)
                    if chunk["choices"][0]["delta"].get("content"):
                        yield chunk["choices"][0]["delta"]["content"]

    async def close(self):
        await self.client.aclose()


class DeepSeekProvider(OpenAICompatibleProvider):
    """DeepSeek provider (OpenAI-compatible)."""

    def __init__(self, config: ModelConfig):
        config.base_url = config.base_url or "https://api.deepseek.com/v1"
        config.model = config.model or "deepseek-chat"
        super().__init__(config)


class LiteLLMProvider(ModelProvider):
    """LiteLLM universal provider (supports 100+ models)."""

    def __init__(self, config: ModelConfig):
        super().__init__(config)
        self.base_url = config.base_url or "http://localhost:4000"  # LiteLLM proxy
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=config.timeout,
        )

    async def complete(
        self,
        messages: List[Message],
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
        stream: bool = False,
    ) -> CompletionResponse:
        payload = {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice

        response = await self.client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        return CompletionResponse(
            content=choice["message"].get("content", ""),
            tool_calls=choice["message"].get("tool_calls"),
            finish_reason=choice.get("finish_reason", "stop"),
            usage=data.get("usage"),
        )

    async def stream_complete(
        self,
        messages: List[Message],
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = None,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self.config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": True,
        }
        async with self.client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    import json
                    chunk = json.loads(data)
                    if chunk["choices"][0]["delta"].get("content"):
                        yield chunk["choices"][0]["delta"]["content"]

    async def close(self):
        await self.client.aclose()


class ModelProviderFactory:
    """Factory for creating model providers."""

    _providers: Dict[str, ModelProvider] = {}

    @classmethod
    def create(cls, config: ModelConfig) -> ModelProvider:
        """Create a model provider from config."""
        key = f"{config.provider}:{config.model}"
        if key in cls._providers:
            return cls._providers[key]

        if config.provider == "deepseek":
            provider = DeepSeekProvider(config)
        elif config.provider == "openai":
            provider = OpenAICompatibleProvider(config)
        elif config.provider == "litellm":
            provider = LiteLLMProvider(config)
        else:
            # Default to OpenAI-compatible
            provider = OpenAICompatibleProvider(config)

        cls._providers[key] = provider
        return provider

    @classmethod
    def get_provider(cls, provider: str, model: str) -> Optional[Any]:
        key = f"{provider}:{model}"
        return cls._providers.get(key)

    @classmethod
    async def close_all(cls):
        for provider in cls._providers.values():
            if hasattr(provider, "close"):
                await provider.close()
        cls._providers.clear()


# Convenience function
def create_model_provider(
    provider: str,
    model: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    **kwargs,
) -> ModelProvider:
    """Create a model provider with common settings."""
    config = ModelConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        **kwargs,
    )
    return ModelProviderFactory.create(config)