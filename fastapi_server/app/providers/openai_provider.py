from __future__ import annotations

from typing import Any, Callable, Optional

import httpx

from app.core import config
from app.providers.llm_provider import LLMProvider


class OpenAIProviderError(RuntimeError):
    pass


class OpenAIProvider(LLMProvider):
    """Minimal OpenAI-compatible chat completion provider.

    - generate(): non-streaming response
    - stream(): best-effort token callback (fallback implementation)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or config.OPENAI_API_KEY
        self.base_url = (base_url or config.OPENAI_BASE_URL).rstrip("/")
        self.model = self._normalize_model(model or config.LLM_MODEL or "openai/gpt-4o-mini-std")

        if not self.api_key:
            raise OpenAIProviderError("OPENAI_API_KEY is not set")

    def _normalize_model(self, model: str) -> str:
        key = (model or "").strip().lower()
        mapping = {
            "openai/gpt-4o-mini-std": "gpt-4o-mini",
            "openai/gpt-4.1": "gpt-4.1",
        }
        if key in mapping:
            return mapping[key]
        if key.startswith("openai/"):
            return key.split("/", 1)[1]
        return model

    async def generate(self, prompt: str) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers, json=payload)

        if resp.status_code >= 400:
            raise OpenAIProviderError(
                f"OpenAI request failed (status={resp.status_code}): {resp.text}"
            )

        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            raise OpenAIProviderError("Unexpected OpenAI response format") from exc

    async def stream(self, prompt: str, on_token: Callable[[str], Any]) -> None:
        # Best-effort streaming without SSE wiring.
        text = await self.generate(prompt)
        for chunk in text.split():
            result = on_token(chunk + " ")
            if hasattr(result, "__await__"):
                await result
