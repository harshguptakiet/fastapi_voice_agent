from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class NormalizedInteractionInput(BaseModel):
    """Normalized interaction input.

    This is the stable contract between clients (voice/text) and the
    conversation/orchestration layer.
    """

    session_id: str = Field(..., description="Client/session correlation id")
    input_type: Literal["voice", "text"]

    # Pointer to original input (e.g., blob url, recording id, request id)
    raw_input_ref: Optional[str] = None

    # Text to feed the orchestrator/LLM layer
    normalized_text: str = Field("", description="Normalized text representation")

    language: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class InteractionCitation(BaseModel):
    index: int
    doc_id: str | None = None
    chunk_id: str | None = None
    score: float | None = None
    document_name: str | None = None
    section_title: str | None = None
    document_version: str | None = None
    source_id: str | None = None
    timestamp: str | None = None
    source_identifier: str | None = None
    source_uri: str | None = None
    topic: str | None = None
    language: str | None = None
    quote: str | None = None


class InteractionResponse(BaseModel):
    interaction: NormalizedInteractionInput
    tenant_id: str
    response_text: str
    response_emotion: str
    citations: list[InteractionCitation] = Field(default_factory=list)
    fallback_triggered: bool = False
    response_time_ms: float | None = None
    timings_ms: dict[str, float] = Field(default_factory=dict)
