from __future__ import annotations

import base64
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class AgentAudioInput(BaseModel):
    audio_b64: str = Field(..., description="Base64 PCM16 mono audio")
    sample_rate_hz: int = Field(16000, ge=8000, le=48000)
    transport: Literal["http", "webrtc", "sip"] = "http"

    @field_validator("audio_b64")
    @classmethod
    def validate_audio_b64(cls, value: str) -> str:
        raw = base64.b64decode(value, validate=True)
        if not raw:
            raise ValueError("audio_b64 decodes to empty audio")
        if len(raw) % 2 != 0:
            raise ValueError("audio_b64 must decode to PCM16 bytes")
        return value


class AgentStreamRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    input_type: Literal["text", "audio", "voice"] = "text"
    text: str | None = None
    audio: AgentAudioInput | None = None
    domain: Literal["religious", "education"] | None = Field(
        default=None,
        description="Which agent to use; required when tenant id does not encode the domain.",
    )
    one_shot_http_audio: bool = Field(
        False,
        description="Skip turn detection for single direct HTTP audio uploads.",
    )
    language: str | None = "en-US"

    provider: str | None = None
    llm_model: str | None = None

    use_knowledge: bool = True
    knowledge_top_k: int = Field(3, ge=1, le=10)
    access_level: str | None = None

    output_audio: bool = True
    tts_voice: str | None = None
    tts_format: str | None = None
    tts_emotion: str | None = None

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        text = value.strip()
        return text or None

    @model_validator(mode="after")
    def _validate_input_payload(self) -> "AgentStreamRequest":
        """Ensure text/audio matches input_type (voice = transcript-only, same memory path as audio)."""
        it = self.input_type
        if it in ("text", "voice"):
            if not (self.text or "").strip():
                raise ValueError("text is required when input_type is text or voice")
        if it == "audio" and self.audio is None:
            raise ValueError("audio is required when input_type is audio")
        return self
