import re
from typing import Generator

from fastapi import Header, HTTPException

from app.core.database import SessionLocal
from app.core import config
from app.providers.llm_provider import LLMProvider
from app.providers.disabled_speech_provider import DisabledSpeechProvider
from app.providers.deepgram_elevenlabs_provider import DeepgramElevenLabsProvider
from app.providers.speech_provider import SpeechProvider
from app.services.model_selector import model_selector


def get_db() -> Generator:
    """Return a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_llm_provider() -> LLMProvider:
    """Return the active LLM provider."""
    return model_selector.select(config.LLM_PROVIDER, config.LLM_MODEL)


def get_speech_provider() -> SpeechProvider:
    """Return the active Speech (STT/TTS) provider."""

    if config.USE_DEEPGRAM_ELEVENLABS:
        return DeepgramElevenLabsProvider()

    return DisabledSpeechProvider()


def get_tenant_id(x_tenant_id: str | None = Header(default=None)) -> str:
    """Resolve and validate tenant ID from request headers."""
    tenant_id = (x_tenant_id or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Missing X-Tenant-Id header")
    if len(tenant_id) > 64:
        raise HTTPException(status_code=400, detail="X-Tenant-Id must be <= 64 characters")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", tenant_id):
        raise HTTPException(
            status_code=400,
            detail="X-Tenant-Id contains invalid characters",
        )
    return tenant_id
