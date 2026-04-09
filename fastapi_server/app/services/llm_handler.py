from __future__ import annotations

from app.core import config
from .model_selector import model_selector


class LLMHandler:
    def _resolve_model_for_provider(
        self,
        normalized_provider: str,
        *,
        llm_model: str | None,
    ) -> str | None:
        if llm_model:
            return llm_model

        if normalized_provider == "gemini":
            return config.GEMINI_MODEL
        if normalized_provider == "anthropic":
            return config.ANTHROPIC_MODEL
        if normalized_provider == "openai":
            return config.LLM_MODEL
        return None

    def _select_provider(
        self,
        provider: str | None,
        *,
        llm_model: str | None,
        legacy_model: str | None,
    ):
        # Back-compat: `model` used to mean provider name.
        provider_name = (provider or legacy_model or config.LLM_PROVIDER)
        normalized_provider = model_selector.normalize_provider(provider_name)
        model_name = self._resolve_model_for_provider(
            normalized_provider,
            llm_model=llm_model,
        )
        # DEBUG: Print provider, model, and Gemini API key
        import os
        print(f"[LLM DEBUG] Provider: {provider_name}, Model: {model_name}, GEMINI_API_KEY: {os.getenv('GEMINI_API_KEY')}")
        return model_selector.select(provider_name, model_name)

    async def generate_response(
        self,
        text: str,
        provider: str | None = None,
        *,
        llm_model: str | None = None,
        model: str | None = None,
    ):
        selected = self._select_provider(
            provider,
            llm_model=llm_model,
            legacy_model=model,
        )
        return await selected.generate(text)

    async def stream_response(
        self,
        text: str,
        provider: str | None = None,
        on_token=None,
        *,
        llm_model: str | None = None,
        model: str | None = None,
    ):
        selected = self._select_provider(
            provider,
            llm_model=llm_model,
            legacy_model=model,
        )
        return await selected.stream(text, on_token)
