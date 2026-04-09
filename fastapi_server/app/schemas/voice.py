from __future__ import annotations

import base64
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class TranscriptSegment(BaseModel):
    start_ms: int | None = None
    end_ms: int | None = None
    text: str | None = None
    confidence: float | None = None


class NormalizedTranscript(BaseModel):
    request_id: str = Field(..., description="Unique request identifier")
    provider: str = Field(..., description="Speech provider name")
    text: str = Field("", description="Final transcript text")
    language: str | None = Field(None, description="BCP-47 language code")
    confidence: float | None = Field(None, description="Overall confidence, if available")
    segments: list[TranscriptSegment] = Field(default_factory=list)

    # Keep provider-specific data optional and off by default.
    raw: Optional[dict[str, Any]] = None


class Pcm16Base64Audio(BaseModel):
    """Base64-encoded PCM16 mono audio."""

    audio_b64: str = Field(..., description="Base64-encoded PCM16 mono audio")
    sample_rate_hz: int = Field(
        24000,
        ge=8000,
        le=48000,
        description="Sample rate in Hz (commonly 16000 or 24000)",
    )

    @field_validator("audio_b64")
    @classmethod
    def _validate_base64_pcm(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("audio_b64 is required")

        try:
            raw = base64.b64decode(v, validate=True)
        except Exception as exc:
            raise ValueError("audio_b64 must be valid base64") from exc

        # PCM16 mono -> byte length must be even.
        if len(raw) % 2 != 0:
            raise ValueError("audio_b64 does not decode to valid PCM16")
        if len(raw) == 0:
            raise ValueError("audio_b64 decodes to empty audio")

        # Guardrail against oversized requests.
        if len(raw) > 10_000_000:
            raise ValueError("audio_b64 audio is too large")

        return v


class TranscribeAudioRequest(BaseModel):
    """Speech-to-text request."""

    audio: Pcm16Base64Audio
    language: str | None = Field(None, description="BCP-47 language code, e.g. en-US")
    request_id: str | None = Field(None, description="Client-supplied request id")


class VoiceInfo(BaseModel):
    name: str
    locale: str | None = None
    gender: str | None = None
    provider: str | None = None


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Text to synthesize")
    language: str | None = Field(None, description="Optional language hint")
    voice: str | None = Field(None, description="Optional voice name")
    emotion: str | None = Field(None, description="Optional emotion hint for expressive TTS")
    request_id: str | None = Field(None, description="Client-supplied request id")
    output_format: str | None = Field(
        None,
        description="Optional provider format hint, e.g. mp3 or wav",
    )


class SynthesizeResponse(BaseModel):
    request_id: str
    provider: str
    voice: str | None = None
    mime_type: str = "audio/wav"
    audio_b64: str = Field(..., description="Base64-encoded audio")
    raw: Optional[dict[str, Any]] = None
