from __future__ import annotations

import uuid
import re
from typing import Any, Optional

import httpx

from app.core import config
from app.providers.speech_provider import SpeechProvider
from app.schemas.voice import NormalizedTranscript, TranscriptSegment


class DeepgramElevenLabsError(RuntimeError):
    """Raised when Deepgram or ElevenLabs call fails."""


class DeepgramElevenLabsProvider(SpeechProvider):
    """SpeechProvider backed by Deepgram STT and ElevenLabs TTS."""

    @property
    def name(self) -> str:
        return "deepgram-elevenlabs"

    def _normalize_elevenlabs_model(self, model: str) -> str:
        key = (model or "").strip().lower()
        mapping = {
            "elevenlabs/flash-v2.5": "eleven_flash_v2_5",
        }
        if key in mapping:
            return mapping[key]
        if key.startswith("elevenlabs/"):
            return key.split("/", 1)[1]
        return model

    def _normalize_emotion(self, emotion: Optional[str]) -> str | None:
        if not emotion:
            return None
        key = emotion.strip().lower()
        allowed = {
            "calm", "excited", "empathetic", "confident",
            "cheerful", "serious", "reassuring", "playful", "urgent",
        }
        return key if key in allowed else None

    def _emotion_to_voice_settings(self, emotion: Optional[str]) -> dict[str, float | bool] | None:
        e = self._normalize_emotion(emotion)
        if not e:
            return None
        mapping: dict[str, dict[str, float | bool]] = {
            "calm": {"stability": 0.72, "similarity_boost": 0.7, "style": 0.15, "use_speaker_boost": True},
            "excited": {"stability": 0.38, "similarity_boost": 0.7, "style": 0.9, "use_speaker_boost": True},
            "empathetic": {"stability": 0.58, "similarity_boost": 0.72, "style": 0.45, "use_speaker_boost": True},
            "confident": {"stability": 0.56, "similarity_boost": 0.75, "style": 0.62, "use_speaker_boost": True},
            "cheerful": {"stability": 0.46, "similarity_boost": 0.72, "style": 0.82, "use_speaker_boost": True},
            "serious": {"stability": 0.78, "similarity_boost": 0.75, "style": 0.18, "use_speaker_boost": True},
            "reassuring": {"stability": 0.66, "similarity_boost": 0.72, "style": 0.34, "use_speaker_boost": True},
            "playful": {"stability": 0.42, "similarity_boost": 0.68, "style": 0.86, "use_speaker_boost": True},
            "urgent": {"stability": 0.82, "similarity_boost": 0.75, "style": 0.5, "use_speaker_boost": True},
        }
        return mapping.get(e)

    def _strip_emotion_label(self, text: str) -> str:
        raw = (text or "").strip()
        return re.sub(r"^\[emotion:\s*[a-zA-Z-]+\]\s*", "", raw, flags=re.IGNORECASE).strip()

    async def health_check(self) -> bool:
        if not config.DEEPGRAM_API_KEY or not config.ELEVENLABS_API_KEY:
            return False

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                voices_resp = await client.get(
                    f"{config.ELEVENLABS_BASE_URL.rstrip('/')}/voices",
                    headers={"xi-api-key": config.ELEVENLABS_API_KEY},
                )
        except httpx.HTTPError as exc:
            raise DeepgramElevenLabsError(f"Health check failed: {exc}") from exc

        return voices_resp.status_code < 500

    async def transcribe_wav(
        self,
        *,
        wav_bytes: bytes,
        sample_rate_hz: int,
        language: Optional[str] = None,
        request_id: Optional[str] = None,
    ) -> NormalizedTranscript:
        if not config.DEEPGRAM_API_KEY:
            raise DeepgramElevenLabsError("DEEPGRAM_API_KEY is not set")

        rid = request_id or str(uuid.uuid4())
        lang = (language or config.DEEPGRAM_LANGUAGE or "en-US").strip() or "en-US"

        params = {
            "model": config.DEEPGRAM_MODEL,
            "language": lang,
            "smart_format": "true",
            "punctuate": "true",
        }

        headers = {
            "Authorization": f"Token {config.DEEPGRAM_API_KEY}",
            "Content-Type": f"audio/wav; rate={sample_rate_hz}",
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                config.DEEPGRAM_STT_URL,
                params=params,
                headers=headers,
                content=wav_bytes,
            )

        if resp.status_code >= 400:
            raise DeepgramElevenLabsError(
                f"Deepgram STT request failed (status={resp.status_code})"
            )

        try:
            data: dict[str, Any] = resp.json()
        except Exception as exc:
            raise DeepgramElevenLabsError("Invalid Deepgram STT response") from exc

        results = data.get("results") if isinstance(data, dict) else None
        channels = results.get("channels") if isinstance(results, dict) else None
        first_channel = channels[0] if isinstance(channels, list) and channels else {}
        alternatives = first_channel.get("alternatives") if isinstance(first_channel, dict) else None
        first_alt = alternatives[0] if isinstance(alternatives, list) and alternatives else {}

        text = first_alt.get("transcript") if isinstance(first_alt, dict) else ""
        confidence_raw = first_alt.get("confidence") if isinstance(first_alt, dict) else None
        confidence = float(confidence_raw) if isinstance(confidence_raw, (int, float)) else None

        words = first_alt.get("words") if isinstance(first_alt, dict) else None
        segments: list[TranscriptSegment] = []
        if isinstance(words, list):
            for word in words:
                if not isinstance(word, dict):
                    continue
                start = word.get("start")
                end = word.get("end")
                w_text = word.get("word")
                w_conf = word.get("confidence")
                segments.append(
                    TranscriptSegment(
                        start_ms=int(float(start) * 1000) if isinstance(start, (int, float)) else None,
                        end_ms=int(float(end) * 1000) if isinstance(end, (int, float)) else None,
                        text=w_text if isinstance(w_text, str) else None,
                        confidence=float(w_conf) if isinstance(w_conf, (int, float)) else None,
                    )
                )

        return NormalizedTranscript(
            request_id=rid,
            provider=self.name,
            text=text.strip() if isinstance(text, str) else "",
            language=lang,
            confidence=confidence,
            segments=segments,
            raw=None,
        )

    async def list_voices(self) -> list[dict]:
        if not config.ELEVENLABS_API_KEY:
            raise DeepgramElevenLabsError("ELEVENLABS_API_KEY is not set")

        url = f"{config.ELEVENLABS_BASE_URL.rstrip('/')}/voices"

        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(url, headers={"xi-api-key": config.ELEVENLABS_API_KEY})

        if resp.status_code >= 400:
            raise DeepgramElevenLabsError(
                f"ElevenLabs voices list failed (status={resp.status_code})"
            )

        try:
            payload = resp.json()
        except Exception as exc:
            raise DeepgramElevenLabsError("Invalid ElevenLabs voices response") from exc

        voices_raw = payload.get("voices") if isinstance(payload, dict) else None
        if not isinstance(voices_raw, list):
            return []

        voices: list[dict] = []
        for item in voices_raw:
            if not isinstance(item, dict):
                continue
            labels = item.get("labels") if isinstance(item.get("labels"), dict) else {}
            accent = labels.get("accent") if isinstance(labels, dict) else None
            locale = accent if isinstance(accent, str) and accent.strip() else None
            voices.append(
                {
                    "name": item.get("name") or item.get("voice_id"),
                    "locale": locale,
                    "gender": labels.get("gender") if isinstance(labels, dict) else None,
                    "provider": self.name,
                }
            )

        return [v for v in voices if v.get("name")]

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
        if not config.ELEVENLABS_API_KEY:
            raise DeepgramElevenLabsError("ELEVENLABS_API_KEY is not set")

        voice_id = (voice or config.ELEVENLABS_VOICE_ID or "").strip()
        if not voice_id:
            raise DeepgramElevenLabsError("ELEVENLABS_VOICE_ID is not set")

        rid = request_id or str(uuid.uuid4())

        fmt = (output_format or "mp3_44100_128").strip()
        mime = "audio/mpeg" if fmt.startswith("mp3") else "audio/wav"

        url = f"{config.ELEVENLABS_BASE_URL.rstrip('/')}/text-to-speech/{voice_id}"
        payload = {
            "text": self._strip_emotion_label(text),
            "model_id": self._normalize_elevenlabs_model(config.ELEVENLABS_MODEL_ID),
            "output_format": fmt,
        }
        voice_settings = self._emotion_to_voice_settings(emotion)
        if voice_settings:
            payload["voice_settings"] = voice_settings

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                url,
                headers={
                    "xi-api-key": config.ELEVENLABS_API_KEY,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg" if mime == "audio/mpeg" else "audio/wav",
                },
                json=payload,
            )

        if resp.status_code >= 400:
            raise DeepgramElevenLabsError(
                f"ElevenLabs TTS request failed (status={resp.status_code}): {resp.text}"
            )

        return (resp.content, mime, voice_id, rid)
