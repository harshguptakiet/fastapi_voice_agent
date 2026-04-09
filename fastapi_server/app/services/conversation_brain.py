
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, AsyncGenerator

from app.providers.speech_provider import SpeechProvider
from app.schemas.agent import AgentStreamRequest
from app.schemas.interaction import NormalizedInteractionInput
from app.services.orchestrator import orchestrator
from app.services.response_guard_service import response_guard_service
from app.services.sentence_buffer_service import sentence_buffer_service


class ConversationBrain:
    """Orchestrates cache/tools/session/retrieval/LLM and emits text/audio streams."""

    def _sanitize_user_input(self, text: str) -> str:
        # Remove dangerous characters, excessive length, and prompt injection patterns
        t = (text or "")[:500]
        t = re.sub(r"[\u202e\u202d\u202c\u202a\u202b]", "", t)  # Remove Unicode control chars
        t = re.sub(r"[\r\n\t]", " ", t)
        t = re.sub(r"\b(ignore|disregard|pretend|you are now|system:|user:|assistant:|as an ai|jailbreak|prompt injection)\b", "", t, flags=re.I)
        return t.strip()

    async def stream(
        self,
        *,
        interaction: NormalizedInteractionInput,
        body: AgentStreamRequest,
        provider: SpeechProvider,
        tenant_id: str,
    ) -> AsyncGenerator[dict[str, Any], None]:
        token_parts: list[str] = []
        metrics_payload: dict[str, Any] = {}
        final_text_override: str | None = None

        # Sanitize user input before LLM call
        if hasattr(interaction, "normalized_text"):
            interaction.normalized_text = self._sanitize_user_input(interaction.normalized_text)

        # Track if a final_text event was received from orchestrator
        got_final_text_event = False
        tts_tail = ""
        audio_idx = 0
        tts_enabled = bool(body.output_audio)
        tts_error: str | None = None

        async for event in orchestrator.stream_interaction(
            interaction,
            provider=body.provider,
            llm_model=body.llm_model,
            tenant_id=tenant_id,
            access_level=body.access_level,
            use_knowledge=body.use_knowledge,
            knowledge_top_k=body.knowledge_top_k,
        ):
            name = str(event.get("event") or "message")
            data = event.get("data")

            if name == "token" and isinstance(data, str):
                token_parts.append(data)
                yield {"event": "text", "data": data}
                if tts_enabled:
                    tts_tail += data
                    ready, tts_tail = sentence_buffer_service.pop_leading_speech_chunks(tts_tail)
                    for chunk in ready:
                        try:
                            (
                                audio_bytes,
                                mime,
                                voice_used,
                                request_id,
                            ) = await provider.synthesize_text(
                                text=chunk,
                                language=body.language,
                                voice=body.tts_voice,
                                emotion=body.tts_emotion,
                                request_id=None,
                                output_format=body.tts_format,
                            )
                        except Exception as exc:
                            # Do not abort the whole turn if TTS is unavailable (quota/network/etc).
                            tts_enabled = False
                            tts_error = str(exc)
                            yield {
                                "event": "status",
                                "data": "Voice output unavailable right now. Continuing with text response.",
                            }
                            break

                        yield {
                            "event": "audio",
                            "data": {
                                "index": audio_idx,
                                "text": chunk,
                                "request_id": request_id,
                                "voice": voice_used,
                                "mime_type": mime,
                                "audio_b64": self._to_b64(audio_bytes),
                            },
                        }
                        audio_idx += 1
                        await asyncio.sleep(0)
                continue

            if name == "metrics" and isinstance(data, str):
                try:
                    metrics_payload = json.loads(data)
                except Exception:
                    metrics_payload = {"parse_error": data}
                yield {"event": "metrics", "data": metrics_payload}
                continue

            if name == "final_text" and isinstance(data, str):
                final_text_override = data.strip() or None
                got_final_text_event = True
                continue

            if name == "done":
                break

            if name == "message" and isinstance(data, str):
                yield {"event": "status", "data": data}

        full_text = "".join(token_parts).strip()
        final_text = final_text_override or full_text

        # Orchestrator may emit `final_text` during streaming; we currently swallow it above,
        # so we emit exactly once here for the client to render a bot chat bubble.
        if final_text:
            # Keep short speech-safe responses for voice/TTS, but allow fuller text-mode output.
            if body.output_audio or interaction.input_type == "voice":
                guarded = response_guard_service.enforce(final_text)
            else:
                guarded = response_guard_service.enforce(final_text, max_sentences=6, max_words=220)
            yield {"event": "final_text", "data": guarded}

        if body.output_audio and tts_enabled:
            if audio_idx == 0 and final_text:
                # No token stream audio — speak full reply (e.g. orchestrator emitted final only).
                chunks = sentence_buffer_service.split_for_tts(final_text)
                for chunk in chunks:
                    try:
                        audio_bytes, mime, voice_used, request_id = await provider.synthesize_text(
                            text=chunk,
                            language=body.language,
                            voice=body.tts_voice,
                            emotion=body.tts_emotion,
                            request_id=None,
                            output_format=body.tts_format,
                        )
                    except Exception as exc:
                        tts_enabled = False
                        tts_error = str(exc)
                        break
                    yield {
                        "event": "audio",
                        "data": {
                            "index": audio_idx,
                            "text": chunk,
                            "request_id": request_id,
                            "voice": voice_used,
                            "mime_type": mime,
                            "audio_b64": self._to_b64(audio_bytes),
                        },
                    }
                    audio_idx += 1
                    await asyncio.sleep(0)
            elif tts_tail.strip():
                for chunk in sentence_buffer_service.split_for_tts(tts_tail.strip()):
                    try:
                        audio_bytes, mime, voice_used, request_id = await provider.synthesize_text(
                            text=chunk,
                            language=body.language,
                            voice=body.tts_voice,
                            emotion=body.tts_emotion,
                            request_id=None,
                            output_format=body.tts_format,
                        )
                    except Exception as exc:
                        tts_enabled = False
                        tts_error = str(exc)
                        break
                    yield {
                        "event": "audio",
                        "data": {
                            "index": audio_idx,
                            "text": chunk,
                            "request_id": request_id,
                            "voice": voice_used,
                            "mime_type": mime,
                            "audio_b64": self._to_b64(audio_bytes),
                        },
                    }
                    audio_idx += 1
                    await asyncio.sleep(0)

        yield {
            "event": "done",
            "data": {
                "ok": True,
                "timings_ms": metrics_payload,
                "tts_error": tts_error,
            },
        }

    def _to_b64(self, data: bytes) -> str:
        import base64

        return base64.b64encode(data).decode("ascii")


conversation_brain = ConversationBrain()
