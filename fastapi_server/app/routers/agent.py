from __future__ import annotations

import base64
import io
import json
import re
import uuid
import wave


import logging
logging.basicConfig(level=logging.INFO)
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.dependencies import get_speech_provider, get_tenant_id
from app.providers.speech_provider import SpeechProvider
from app.schemas.agent import AgentStreamRequest, AgentAudioInput

from app.services.conversation_brain import conversation_brain
from app.services.input_router import input_router
from app.core.intent_guard import is_allowed_intent, RELIGIOUS_FALLBACK, EDUCATION_FALLBACK

logger = logging.getLogger("agent_debug")


router = APIRouter(prefix="/agent", tags=["agent"])


def sse_event(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


def _validate_tenant_id(tenant_id: str | None) -> str:
    value = (tenant_id or "").strip()
    if not value:
        raise ValueError("Missing X-Tenant-Id header")
    if len(value) > 64:
        raise ValueError("X-Tenant-Id must be <= 64 characters")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", value):
        raise ValueError("X-Tenant-Id contains invalid characters")
    return value


def _pcm16_to_wav(pcm16_bytes: bytes, sample_rate_hz: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate_hz)
        wf.writeframes(pcm16_bytes)
    return buf.getvalue()


async def _emit_json(websocket: WebSocket, event: str, data: dict | str) -> None:
    await websocket.send_json({"event": event, "data": data})



@router.post("/stream")
async def stream_agent(
    body: AgentStreamRequest,
    tenant_id: str = Depends(get_tenant_id),
    provider: SpeechProvider = Depends(get_speech_provider),
):
    logger.info("[AGENT DEBUG] Entered stream_agent endpoint")
    async def _generator():
        logger.info("[AGENT DEBUG] Incoming request body: %s", body)

        try:
            interaction, route_meta = await input_router.normalize(body, provider)
        except Exception as exc:
            logger.info("[AGENT DEBUG] input_router.normalize error: %s", exc)
            err = {"ok": False, "error": "input_normalization_failed", "detail": str(exc)}
            yield sse_event("done", json.dumps(err, ensure_ascii=True))
            return

        if interaction is None:
            logger.info("[AGENT DEBUG] interaction is None, route_meta: %s", route_meta)
            yield sse_event("input", json.dumps(route_meta, ensure_ascii=True))
            yield sse_event("done", json.dumps({"ok": False, **route_meta}, ensure_ascii=True))
            return

        # --- GUARDRAIL ENFORCEMENT ---
        domain = None
        tenant = (tenant_id or "").lower()
        print(f"[DEBUG] tenant_id: {tenant_id}, tenant: {tenant}")
        if "religious" in tenant:
            domain = "religious"
        elif "education" in tenant or "eduthum" in tenant:
            domain = "education"
        if hasattr(body, "domain") and body.domain:
            domain = str(body.domain).lower()
        print(f"[DEBUG] body.domain: {getattr(body, 'domain', None)}")
        print(f"[DEBUG] resolved domain: {domain}")

        user_text = getattr(interaction, "normalized_text", None) or ""
        print(f"[DEBUG] user_text: {user_text}")
        logger.info(f"[AGENT DEBUG] user_text: {user_text}, domain: {domain}")
        allowed, explanation = is_allowed_intent(user_text, domain)
        logger.info(f"[AGENT DEBUG] is_allowed_intent: {allowed}, explanation: {explanation}")
        print(f"[DEBUG] is_allowed_intent: {allowed}, explanation: {explanation}")
        if allowed != "YES":
            logger.info(f"[AGENT DEBUG] Blocked by guardrail: {explanation}")
            if domain == "religious":
                yield sse_event("final_text", RELIGIOUS_FALLBACK)
                yield sse_event("done", json.dumps({"ok": True, "guardrail": "religious", "explanation": explanation}, ensure_ascii=True))
            elif domain == "education":
                yield sse_event("final_text", EDUCATION_FALLBACK)
                yield sse_event("done", json.dumps({"ok": True, "guardrail": "education", "explanation": explanation}, ensure_ascii=True))
            else:
                yield sse_event("final_text", "Sorry, I can't assist with that.")
                yield sse_event("done", json.dumps({"ok": True, "guardrail": "default", "explanation": explanation}, ensure_ascii=True))
            return

        yield sse_event("input", json.dumps(route_meta, ensure_ascii=True))

        try:
            async for event in conversation_brain.stream(
                interaction=interaction,
                body=body,
                provider=provider,
                tenant_id=tenant_id,
            ):
                name = str(event.get("event") or "message")
                payload = event.get("data")
                serialized = payload if isinstance(payload, str) else json.dumps(payload or {}, ensure_ascii=True)
                yield sse_event(name, serialized)
        except Exception as exc:
            err = {"ok": False, "error": "llm_or_stream_failed", "detail": str(exc)}
            yield sse_event("done", json.dumps(err, ensure_ascii=True))
            return

    return StreamingResponse(_generator(), media_type="text/event-stream")


@router.websocket("/ws")
async def stream_agent_ws(
    websocket: WebSocket,
    provider: SpeechProvider = Depends(get_speech_provider),
):
    await websocket.accept()

    try:
        tenant_id = _validate_tenant_id(
            websocket.headers.get("x-tenant-id") or websocket.query_params.get("tenant_id")
        )
    except ValueError as exc:
        await _emit_json(websocket, "error", {"reason": str(exc)})
        await websocket.close(code=1008)
        return

    session_id = f"voice-{uuid.uuid4()}"
    sample_rate_hz = 16000
    language = "en-US"
    llm_provider = None
    llm_model = None
    use_knowledge = True
    knowledge_top_k = 3
    access_level = None
    output_audio = True
    tts_voice = None
    tts_format = None
    tts_emotion = None
    one_shot_http_audio = True
    selected_domain = None

    audio_buffer = bytearray()

    async def process_turn() -> None:
        nonlocal audio_buffer

        if not audio_buffer:
            await _emit_json(websocket, "done", {"ok": False, "reason": "missing_audio"})
            return

        request_body = AgentStreamRequest(
            session_id=session_id,
            input_type="audio",
            audio=AgentAudioInput(
                audio_b64=base64.b64encode(bytes(audio_buffer)).decode("ascii"),
                sample_rate_hz=sample_rate_hz,
                transport="http",
            ),
            domain=selected_domain,
            one_shot_http_audio=one_shot_http_audio,
            language=language,
            provider=llm_provider,
            llm_model=llm_model,
            use_knowledge=use_knowledge,
            knowledge_top_k=knowledge_top_k,
            access_level=access_level,
            output_audio=output_audio,
            tts_voice=tts_voice,
            tts_format=tts_format,
            tts_emotion=tts_emotion,
        )

        interaction, route_meta = await input_router.normalize(request_body, provider)
        await _emit_json(websocket, "input", route_meta)

        # --- GUARDRAIL ENFORCEMENT (same as /stream) ---
        domain = None
        tenant = (tenant_id or "").lower()
        if "religious" in tenant:
            domain = "religious"
        elif "education" in tenant or "eduthum" in tenant:
            domain = "education"
        # Optionally, allow explicit domain in request_body
        if hasattr(request_body, "domain") and request_body.domain:
            domain = str(request_body.domain).lower()

        user_text = getattr(interaction, "normalized_text", None) or ""
        allowed, explanation = is_allowed_intent(user_text, domain)
        if allowed != "YES":
            if domain == "religious":
                await _emit_json(websocket, "final_text", RELIGIOUS_FALLBACK)
                await _emit_json(websocket, "done", {"ok": True, "guardrail": "religious", "explanation": explanation})
            elif domain == "education":
                await _emit_json(websocket, "final_text", EDUCATION_FALLBACK)
                await _emit_json(websocket, "done", {"ok": True, "guardrail": "education", "explanation": explanation})
            else:
                await _emit_json(websocket, "final_text", "Sorry, I can't assist with that.")
                await _emit_json(websocket, "done", {"ok": True, "guardrail": "default", "explanation": explanation})
            audio_buffer = bytearray()
            return

        if interaction is None:
            await _emit_json(websocket, "done", {"ok": False, **route_meta})
            audio_buffer = bytearray()
            return

        async for event in conversation_brain.stream(
            interaction=interaction,
            body=request_body,
            provider=provider,
            tenant_id=tenant_id,
        ):
            await _emit_json(websocket, str(event.get("event") or "message"), event.get("data") or {})

        audio_buffer = bytearray()

    await _emit_json(websocket, "ready", {"session_id": session_id})

    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = str(msg.get("type") or "").strip().lower()

            if msg_type == "start":
                session_id = str(msg.get("session_id") or session_id)
                sample_rate_hz = int(msg.get("sample_rate_hz") or sample_rate_hz)
                language = str(msg.get("language") or language)
                incoming_domain = str(msg.get("domain") or "").strip().lower()
                selected_domain = (
                    incoming_domain if incoming_domain in {"religious", "education"} else None
                )
                llm_provider = msg.get("provider")
                llm_model = msg.get("llm_model")
                use_knowledge = bool(msg.get("use_knowledge", use_knowledge))
                knowledge_top_k = int(msg.get("knowledge_top_k") or knowledge_top_k)
                access_level = msg.get("access_level")
                output_audio = bool(msg.get("output_audio", output_audio))
                tts_voice = msg.get("tts_voice")
                tts_format = msg.get("tts_format")
                tts_emotion = msg.get("tts_emotion")
                one_shot_http_audio = bool(msg.get("one_shot_http_audio", one_shot_http_audio))

                audio_buffer = bytearray()
                await _emit_json(websocket, "started", {"session_id": session_id})
                continue

            if msg_type == "audio_chunk":
                audio_b64 = str(msg.get("audio_b64") or "")
                if not audio_b64:
                    await _emit_json(websocket, "error", {"reason": "missing_audio_chunk"})
                    continue

                try:
                    raw_chunk = base64.b64decode(audio_b64, validate=True)
                except Exception:
                    await _emit_json(websocket, "error", {"reason": "invalid_audio_chunk_base64"})
                    continue

                if not raw_chunk or len(raw_chunk) % 2 != 0:
                    await _emit_json(websocket, "error", {"reason": "invalid_pcm16_chunk"})
                    continue

                audio_buffer.extend(raw_chunk)
                # Recorded-audio mode: append chunks and wait for explicit finalize.
                buffered_ms = int((len(audio_buffer) / 2.0) / max(sample_rate_hz, 1) * 1000)
                await _emit_json(
                    websocket,
                    "audio_progress",
                    {
                        "buffered_ms": buffered_ms,
                        "buffer_bytes": len(audio_buffer),
                    },
                )
                continue

            if msg_type == "finalize":
                await process_turn()
                continue

            if msg_type == "ping":
                await _emit_json(websocket, "pong", {"ok": True})
                continue

            if msg_type == "stop":
                await _emit_json(websocket, "stopped", {"ok": True})
                break

            await _emit_json(websocket, "error", {"reason": "unsupported_message_type"})

    except WebSocketDisconnect:
        return
    except Exception as exc:
        await _emit_json(websocket, "error", {"reason": str(exc)})
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
