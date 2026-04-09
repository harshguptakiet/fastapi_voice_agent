from __future__ import annotations

import io
import uuid
import wave
from typing import Optional

from app.providers.speech_provider import SpeechProvider
from app.schemas.voice import NormalizedTranscript


class DisabledSpeechProvider(SpeechProvider):
    """Speech provider used when voice is disabled by configuration."""

    @property
    def name(self) -> str:
        return "disabled"

    async def health_check(self) -> bool:
        return False

    async def transcribe_wav(
        self,
        *,
        wav_bytes: bytes,
        sample_rate_hz: int,
        language: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> NormalizedTranscript:
        return NormalizedTranscript(
            request_id=request_id or str(uuid.uuid4()),
            provider=self.name,
            text="",
            language=(language or None),
            confidence=None,
            segments=[],
            raw={"status": "disabled"},
        )

    async def list_voices(self) -> list[dict]:
        return []

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
        # Return a short silent WAV so callers can exercise the pipeline locally.
        rid = request_id or str(uuid.uuid4())
        sample_rate_hz = 16000
        duration_ms = 200
        frames = int(sample_rate_hz * duration_ms / 1000)
        silence_pcm16 = b"\x00\x00" * frames

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate_hz)
            wf.writeframes(silence_pcm16)

        return (buf.getvalue(), "audio/wav", voice, rid)
