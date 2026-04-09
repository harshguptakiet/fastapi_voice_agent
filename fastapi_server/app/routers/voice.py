import base64
import io
import asyncio
import uuid
import wave

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_speech_provider
from app.providers.deepgram_elevenlabs_provider import DeepgramElevenLabsError
from app.providers.disabled_speech_provider import DisabledSpeechProvider
from app.providers.speech_provider import SpeechProvider
from app.schemas.voice import (
    NormalizedTranscript,
    SynthesizeRequest,
    SynthesizeResponse,
    TranscribeAudioRequest,
    VoiceInfo,
)
from app.services.embedding_service import embedding_service


router = APIRouter(prefix="/voice", tags=["voice"])


@router.get("/health")
async def voice_health(provider: SpeechProvider = Depends(get_speech_provider)) -> dict[str, str]:
    if isinstance(provider, DisabledSpeechProvider):
        return {"status": "disabled"}

    try:
        ok = await provider.health_check()
    except Exception:
        return {"status": "unhealthy"}

    return {"status": "ok" if ok else "unhealthy"}


@router.post("/transcribe", response_model=NormalizedTranscript)
async def transcribe_audio(
    body: TranscribeAudioRequest,
    provider: SpeechProvider = Depends(get_speech_provider),
) -> NormalizedTranscript:
    if isinstance(provider, DisabledSpeechProvider):
        return await provider.transcribe_wav(
            wav_bytes=b"",
            sample_rate_hz=body.audio.sample_rate_hz,
            language=body.language,
            request_id=body.request_id,
        )

    raw_pcm = base64.b64decode(body.audio.audio_b64)

    sample_rate = body.audio.sample_rate_hz
    request_id = body.request_id or str(uuid.uuid4())
    language = body.language

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(raw_pcm)

    try:
        transcript = await provider.transcribe_wav(
            wav_bytes=buf.getvalue(),
            sample_rate_hz=sample_rate,
            language=language,
            request_id=request_id,
        )
        if (transcript.confidence or 0.0) >= 0.85 and transcript.text:
            # Prewarm embedding in background so retrieval can start faster in next step.
            asyncio.create_task(embedding_service.embed_text_async(transcript.text))
        return transcript
    except DeepgramElevenLabsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="STT request failed") from exc


@router.get("/voices", response_model=list[VoiceInfo])
async def list_voices(
    provider: SpeechProvider = Depends(get_speech_provider),
) -> list[VoiceInfo]:
    try:
        voices = await provider.list_voices()
    except NotImplementedError:
        return []
    except Exception:
        return []

    out: list[VoiceInfo] = []
    for v in voices:
        if isinstance(v, dict) and v.get("name"):
            out.append(VoiceInfo(**v))
    return out


@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize(
    body: SynthesizeRequest,
    provider: SpeechProvider = Depends(get_speech_provider),
) -> SynthesizeResponse:
    rid = body.request_id or str(uuid.uuid4())
    try:
        audio_bytes, mime, voice_used, final_rid = await provider.synthesize_text(
            text=body.text,
            language=body.language,
            voice=body.voice,
            emotion=body.emotion,
            request_id=rid,
            output_format=body.output_format,
        )
    except DeepgramElevenLabsError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="TTS request failed") from exc

    return SynthesizeResponse(
        request_id=final_rid,
        provider=getattr(provider, "name", provider.__class__.__name__),
        voice=voice_used,
        mime_type=mime,
        audio_b64=base64.b64encode(audio_bytes).decode("ascii"),
        raw=None if not isinstance(provider, DisabledSpeechProvider) else {"status": "disabled"},
    )


