from __future__ import annotations

from typing import Any, Callable, Optional

import httpx

from app.core import config
from app.providers.llm_provider import LLMProvider


class AnthropicProviderError(RuntimeError):
    pass


class AnthropicProvider(LLMProvider):
    """Minimal Anthropic Messages API provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or config.ANTHROPIC_API_KEY
        self.base_url = (base_url or config.ANTHROPIC_BASE_URL).rstrip("/")
        self.model = self._normalize_model(model or config.ANTHROPIC_MODEL or "claude/haiku-4.5")

        if not self.api_key:
            raise AnthropicProviderError("ANTHROPIC_API_KEY is not set")

    def _normalize_model(self, model: str) -> str:
        key = (model or "").strip().lower()
        mapping = {
            "claude/haiku-4.5": "claude-3-5-haiku-latest",
        }
        if key in mapping:
            return mapping[key]
        if key.startswith("anthropic/"):
            return key.split("/", 1)[1]
        return model

    async def generate(self, prompt: str) -> str:
        url = f"{self.base_url}/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }

        async with httpx.AsyncClient(timeout=40.0) as client:
            resp = await client.post(url, headers=headers, json=payload)

        if resp.status_code >= 400:
            raise AnthropicProviderError(
                f"Anthropic request failed (status={resp.status_code}): {resp.text}"
            )

        data = resp.json()
        try:
            content = data.get("content")
            if not isinstance(content, list):
                raise ValueError("content is not a list")
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "".join(parts)
        except Exception as exc:
            raise AnthropicProviderError("Unexpected Anthropic response format") from exc

    async def stream(self, prompt: str, on_token: Callable[[str], Any]) -> None:
        text = await self.generate(prompt)
        for chunk in text.split():
            result = on_token(chunk + " ")
            if hasattr(result, "__await__"):
                await result
