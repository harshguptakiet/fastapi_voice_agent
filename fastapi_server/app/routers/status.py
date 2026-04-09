from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core import config
from app.dependencies import get_db, get_llm_provider, get_speech_provider
from app.providers.disabled_speech_provider import DisabledSpeechProvider
from app.providers.llm_provider import LLMProvider
from app.providers.speech_provider import SpeechProvider
from app.schemas.status import DependencyStatus, SystemStatusResponse
from app.services.embedding_service import embedding_service
from app.services.object_storage_service import object_storage
from app.services.vector_store_service import vector_store


router = APIRouter(prefix="/status", tags=["status"])


@router.get("", response_model=SystemStatusResponse)
async def system_status(
    llm: LLMProvider = Depends(get_llm_provider),
    voice: SpeechProvider = Depends(get_speech_provider),
    _db=Depends(get_db),
) -> SystemStatusResponse:
    # Database health: if dependency injected, consider it ok.
    db_status = DependencyStatus(status="ok")

    # LLM health: if provider resolved, ok.
    llm_status = DependencyStatus(status="ok", detail=llm.__class__.__name__)

    # Voice health:
    if isinstance(voice, DisabledSpeechProvider):
        voice_status = DependencyStatus(status="disabled")
    else:
        try:
            ok = await voice.health_check()
            voice_status = DependencyStatus(status="ok" if ok else "unhealthy")
        except Exception as exc:
            voice_status = DependencyStatus(status="unhealthy", detail=str(exc))

    overall = "ok"
    if voice_status.status in {"unhealthy"}:
        overall = "degraded"

    return SystemStatusResponse(
        status=overall,
        env=config.ENV,
        llm=llm_status,
        voice=voice_status,
        database=db_status,
        tags=["gateway", "fastapi"],
    )


@router.get("/storage")
async def storage_status() -> dict[str, str | bool | None]:
    provider = object_storage.provider
    using_s3 = provider == "s3"
    bucket = object_storage._s3_bucket if using_s3 else None

    return {
        "provider": provider,
        "using_s3": using_s3,
        "bucket": bucket,
        "local_dir": str(object_storage.base_dir),
    }


@router.get("/knowledge")
async def knowledge_status() -> dict[str, str | int | bool]:
    return {
        "embedding_configured_provider": embedding_service.configured_provider,
        "embedding_backend": embedding_service.backend_name,
        "embedding_model": embedding_service.model_name,
        "embedding_dimensions": embedding_service.dimensions,
        "embedding_fallback_used": embedding_service.fallback_used,
        "vector_configured_provider": vector_store.configured_provider,
        "vector_backend": vector_store.backend_name,
        "vector_fallback_used": vector_store.fallback_used,
    }
