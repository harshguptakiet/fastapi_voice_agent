from __future__ import annotations

from app.core import config


def validate_configuration() -> None:
    """Fail fast on invalid or incomplete configuration."""

    llm_provider = (config.LLM_PROVIDER or "").strip().lower()
    llm_model = (config.LLM_MODEL or None)

    if llm_provider not in {
        "dummy",
        "test",
        "openai",
        "gpt",
        "anthropic",
        "claude",
        "haiku",
        "claude-haiku",
        "gemini",
        "google",
        "gemini-flash",
        "flash",
        "offline",
        "local",
    }:
        raise RuntimeError(f"Unsupported LLM_PROVIDER: {config.LLM_PROVIDER}")

    if llm_provider == "openai":
        if not config.OPENAI_API_KEY:
            raise RuntimeError("LLM_PROVIDER=openai requires OPENAI_API_KEY")
        # model optional; OpenAI provider will default if missing.

    if llm_provider in {"anthropic", "claude"}:
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("LLM_PROVIDER=anthropic requires ANTHROPIC_API_KEY")

    if llm_provider in {"gemini", "google"}:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("LLM_PROVIDER=gemini requires GEMINI_API_KEY")

    if llm_provider in {"offline", "local"}:
        # Explicitly fail until an offline adapter is implemented.
        raise RuntimeError(
            "LLM_PROVIDER=offline is not implemented yet. "
            "Select LLM_PROVIDER=dummy, openai, anthropic, or gemini."
        )

    if config.USE_DEEPGRAM_ELEVENLABS:
        if not config.DEEPGRAM_API_KEY:
            raise RuntimeError(
                "USE_DEEPGRAM_ELEVENLABS=true requires DEEPGRAM_API_KEY"
            )
        if not config.ELEVENLABS_API_KEY:
            raise RuntimeError(
                "USE_DEEPGRAM_ELEVENLABS=true requires ELEVENLABS_API_KEY"
            )
        if not config.ELEVENLABS_VOICE_ID:
            raise RuntimeError(
                "USE_DEEPGRAM_ELEVENLABS=true requires ELEVENLABS_VOICE_ID"
            )

    # Silence unused variable warnings while keeping intent explicit.
    _ = llm_model
