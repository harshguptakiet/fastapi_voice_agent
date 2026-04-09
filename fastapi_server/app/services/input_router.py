from __future__ import annotations

import io
import uuid
import wave
from typing import Any

from app.providers.speech_provider import SpeechProvider
from app.schemas.agent import AgentStreamRequest
from app.schemas.interaction import NormalizedInteractionInput
from app.services.audio_gateway import audio_gateway


class InputRouter:
    """Routes text/audio input into a normalized interaction payload."""

    async def normalize(
        self,
        body: AgentStreamRequest,
        provider: SpeechProvider,
    ) -> tuple[NormalizedInteractionInput | None, dict[str, Any]]:
        if body.input_type == "text":
            if not body.text:
                return None, {"reason": "missing_text"}
            interaction = NormalizedInteractionInput(
                session_id=body.session_id,
                input_type="text",
                raw_input_ref=None,
                normalized_text=body.text,
                language=body.language,
            )
            return interaction, {"stage": "text_input"}

        if body.input_type == "voice":
            # Client already transcribed (e.g. Next.js STT); use voice persona + memory like audio path.
            if not body.text:
                return None, {"reason": "missing_text"}
            transcript = body.text.strip()
            interaction = NormalizedInteractionInput(
                session_id=body.session_id,
                input_type="voice",
                raw_input_ref=None,
                normalized_text=transcript,
                language=body.language,
            )
            return interaction, {
                "stage": "voice_transcript",
                "transcript": transcript,
            }

        if body.audio is None:
            return None, {"reason": "missing_audio"}

        pcm16, sample_rate, transport = audio_gateway.normalize(body.audio)

        transcript = await provider.transcribe_wav(
            wav_bytes=self._pcm16_to_wav(pcm16, sample_rate),
            sample_rate_hz=sample_rate,
            language=body.language,
            request_id=str(uuid.uuid4()),
        )
        text = (transcript.text or "").strip()
        if not text:
            return None, {"reason": "empty_transcript", "transport": transport}

        interaction = NormalizedInteractionInput(
            session_id=body.session_id,
            input_type="voice",
            raw_input_ref=None,
            normalized_text=text,
            language=body.language,
        )
        return interaction, {
            "stage": "audio_input",
            "transport": transport,
            "transcript": text,
            "confidence": transcript.confidence,
        }

    def _pcm16_to_wav(self, pcm16_bytes: bytes, sample_rate_hz: int) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate_hz)
            wf.writeframes(pcm16_bytes)
        return buf.getvalue()


input_router = InputRouter()
