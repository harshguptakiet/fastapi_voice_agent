from __future__ import annotations

from typing import Any, Callable

from app.providers.anthropic_provider import AnthropicProvider
from app.providers.gemini_provider import GeminiProvider
from app.providers.llm_provider import LLMProvider
from app.providers.offline_provider import OfflineProvider
from app.providers.openai_provider import OpenAIProvider


class DummyProvider(LLMProvider):
    """Simple local provider for testing."""

    async def generate(self, prompt: str) -> str:
        return f"Dummy response for: {prompt}"

    async def stream(self, prompt: str, on_token: Callable[[str], Any]):
        for ch in "dummy stream response":
            result = on_token(ch)
            if hasattr(result, "__await__"):
                await result  # support async callbacks


class ModelSelector:
    _aliases: dict[str, str] = {
        "dummy": "dummy",
        "test": "dummy",
        "openai": "openai",
        "gpt": "openai",
        "anthropic": "anthropic",
        "claude": "anthropic",
        "haiku": "anthropic",
        "claude-haiku": "anthropic",
        "gemini": "gemini",
        "google": "gemini",
        "gemini-flash": "gemini",
        "flash": "gemini",
        "offline": "offline",
        "local": "offline",
    }

    def normalize_provider(self, provider: str) -> str:
        key = (provider or "dummy").strip().lower()
        normalized = self._aliases.get(key)
        if not normalized:
            raise ValueError(f"Unsupported LLM provider: {provider}")
        return normalized

    def select(self, provider: str, model: str | None = None) -> LLMProvider:
        """Return an LLMProvider by provider name."""

        key = self.normalize_provider(provider)

        if key == "dummy":
            return DummyProvider()
        if key == "openai":
            return OpenAIProvider(model=model)
        if key == "anthropic":
            return AnthropicProvider(model=model)
        if key == "gemini":
            return GeminiProvider(model=model)
        if key == "offline":
            return OfflineProvider()

        raise ValueError(f"Unsupported LLM provider: {provider}")

    def list_supported_providers(self) -> list[dict[str, str]]:
        return [
            {"id": "openai", "label": "OpenAI"},
            {"id": "gemini", "label": "Google Gemini Flash"},
            {"id": "anthropic", "label": "Anthropic Claude"},
            {"id": "dummy", "label": "Dummy (local test)"},
            {"id": "offline", "label": "Offline (not implemented)"},
        ]


model_selector = ModelSelector()
