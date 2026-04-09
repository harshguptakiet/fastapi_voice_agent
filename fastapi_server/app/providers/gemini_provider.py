from __future__ import annotations

import json
from typing import AsyncGenerator
from typing import Any, Callable, Optional

import httpx

from app.core import config
from app.providers.llm_provider import LLMProvider
from app.services.runtime_clients import runtime_clients


class GeminiProviderError(RuntimeError):
    pass


class GeminiProvider(LLMProvider):
    """Minimal Gemini generateContent API provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or config.GEMINI_API_KEY
        self.base_url = (base_url or config.GEMINI_BASE_URL).rstrip("/")
        self.model = self._normalize_model(model or config.GEMINI_MODEL or "google/gemini-flash")

        if not self.api_key:
            raise GeminiProviderError("GEMINI_API_KEY is not set")

    def _normalize_model(self, model: str) -> str:
        key = (model or "").strip().lower()
        mapping = {
            "google/gemini-flash": "gemini-2.0-flash",
            "google/gemini-flash-lite": "gemini-2.0-flash-lite",
            # In this stack, 2.5-flash has produced heavily truncated responses;
            # route to the stable low-latency flash model for conversational output.
            "google/gemini-2.5-flash": "gemini-2.0-flash",
        }
        if key in mapping:
            return mapping[key]
        if key.startswith("google/"):
            return key.split("/", 1)[1]
        return model

    async def generate(self, prompt: str) -> str:
        url = f"{self.base_url}/v1beta/models/{self.model}:generateContent"
        params = {"key": self.api_key}
        max_tokens = max(32, min(int(config.GEMINI_MAX_OUTPUT_TOKENS), 256))
        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "topP": config.GEMINI_TOP_P,
                "maxOutputTokens": max_tokens,
            },
        }

        client = runtime_clients.get_http()
        resp = await client.post(url, params=params, json=payload, timeout=config.GEMINI_TIMEOUT_SECONDS)

        if resp.status_code >= 400:
            raise GeminiProviderError(
                f"Gemini request failed (status={resp.status_code}): {resp.text}"
            )

        data = resp.json()
        try:
            candidates = data.get("candidates")
            if not isinstance(candidates, list) or not candidates:
                raise ValueError("Missing candidates")
            first = candidates[0] if isinstance(candidates[0], dict) else {}
            content = first.get("content") if isinstance(first, dict) else {}
            parts = content.get("parts") if isinstance(content, dict) else []
            texts: list[str] = []
            if isinstance(parts, list):
                for part in parts:
                    if isinstance(part, dict):
                        text = part.get("text")
                        if isinstance(text, str):
                            texts.append(text)
            return "".join(texts)
        except Exception as exc:
            raise GeminiProviderError("Unexpected Gemini response format") from exc

    async def _iter_sse_data(self, resp: httpx.Response) -> AsyncGenerator[str, None]:
        # Parse complete SSE events so multi-line/fragmented JSON payloads are not dropped.
        data_lines: list[str] = []
        async for line in resp.aiter_lines():
            if line == "":
                if data_lines:
                    yield "\n".join(data_lines)
                    data_lines.clear()
                continue

            if line.startswith(":"):
                continue
            if line.startswith("data:"):
                data_lines.append(line.split("data:", 1)[1].lstrip())

        if data_lines:
            yield "\n".join(data_lines)

    async def stream(self, prompt: str, on_token: Callable[[str], Any]) -> None:
        url = f"{self.base_url}/v1beta/models/{self.model}:streamGenerateContent"
        params = {"key": self.api_key, "alt": "sse"}
        max_tokens = max(32, min(int(config.GEMINI_MAX_OUTPUT_TOKENS), 256))
        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "topP": config.GEMINI_TOP_P,
                "maxOutputTokens": max_tokens,
            },
        }

        client = runtime_clients.get_http()
        async with client.stream(
            "POST",
            url,
            params=params,
            json=payload,
            timeout=config.GEMINI_TIMEOUT_SECONDS,
        ) as resp:
            if resp.status_code >= 400:
                raise GeminiProviderError(
                    f"Gemini stream request failed (status={resp.status_code}): {await resp.aread()}"
                )

            async for raw in self._iter_sse_data(resp):
                raw = raw.strip()
                if raw == "[DONE]":
                    break
                try:
                    data = json.loads(raw)
                except Exception:
                    continue

                candidates = data.get("candidates") if isinstance(data, dict) else None
                if not isinstance(candidates, list) or not candidates:
                    continue
                first = candidates[0] if isinstance(candidates[0], dict) else {}
                content = first.get("content") if isinstance(first, dict) else {}
                parts = content.get("parts") if isinstance(content, dict) else []
                if not isinstance(parts, list):
                    continue

                for part in parts:
                    if not isinstance(part, dict):
                        continue
                    token = part.get("text")
                    if isinstance(token, str) and token:
                        result = on_token(token)
                        if hasattr(result, "__await__"):
                            await result
