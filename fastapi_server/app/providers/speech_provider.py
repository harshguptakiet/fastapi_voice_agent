from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.schemas.voice import NormalizedTranscript


class SpeechProvider(ABC):
    """Provider-agnostic speech interface (STT/TTS).

    Minimal contract:
    - STT from canonical WAV bytes returning a normalized transcript.
    - Health check for basic connectivity.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable provider identifier (e.g. 'deepgram-elevenlabs')."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if provider is reachable/healthy."""

    @abstractmethod
    async def transcribe_wav(
        self,
        *,
        wav_bytes: bytes,
        sample_rate_hz: int,
        language: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> NormalizedTranscript:
        """Speech-to-text from canonical WAV audio."""

    async def list_voices(self) -> list[dict]:
        """Return available voices.

        Providers that do not support voice listing may raise NotImplementedError.
        """

        raise NotImplementedError("Voice listing not supported")

    async def synthesize_text(
        self,
        *,
        text: str,
        language: Optional[str] = None,
        voice: Optional[str] = None,
        emotion: Optional[str] = None,
        request_id: Optional[str] = None,
        output_format: Optional[str] = None,
    ) -> tuple[bytes, str, str | None, str]:
        """Text-to-speech.

        Returns: (audio_bytes, mime_type, voice_used, request_id)
        """

        raise NotImplementedError("Text-to-speech not supported")
