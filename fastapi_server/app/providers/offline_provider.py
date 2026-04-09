from __future__ import annotations

from typing import Any, Callable

from app.providers.llm_provider import LLMProvider


class OfflineProvider(LLMProvider):
    """Placeholder for offline LLM adapters."""

    async def generate(self, prompt: str) -> str:
        raise RuntimeError(
            "Offline LLM provider is not configured."
        )

    async def stream(self, prompt: str, on_token: Callable[[str], Any]) -> None:
        raise RuntimeError(
            "Offline LLM streaming is not configured."
        )
