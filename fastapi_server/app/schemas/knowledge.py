from typing import Any

from pydantic import BaseModel, Field


class ReindexRequest(BaseModel):
    doc_id: str
    text: str
    topic: str | None = None
    language: str = "en"
    source_uri: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReindexResponse(BaseModel):
    tenant_id: str
    doc_id: str
    chunks_indexed: int
    embedding_model: str | None = None
    embedding_dimensions: int | None = None


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    filters: dict[str, Any] = Field(default_factory=dict)


class SearchHit(BaseModel):
    chunk_id: str
    doc_id: str
    score: float
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    tenant_id: str
    results: list[SearchHit]
    embedding_model: str | None = None


class EvaluateCase(BaseModel):
    query: str
    expected_doc_id: str
    top_k: int = 5
    filters: dict[str, Any] = Field(default_factory=dict)


class EvaluateCaseResult(BaseModel):
    query: str
    expected_doc_id: str
    hit: bool
    rank: int | None = None
    returned_doc_ids: list[str] = Field(default_factory=list)


class EvaluateRequest(BaseModel):
    cases: list[EvaluateCase] = Field(default_factory=list)


class EvaluateResponse(BaseModel):
    tenant_id: str
    total_cases: int
    hits: int
    hit_rate: float
    results: list[EvaluateCaseResult] = Field(default_factory=list)
