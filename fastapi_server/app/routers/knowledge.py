import asyncio

from fastapi import APIRouter, Depends

from app.core import config
from app.dependencies import get_tenant_id
from app.schemas.knowledge import (
    EvaluateCaseResult,
    EvaluateRequest,
    EvaluateResponse,
    ReindexRequest,
    ReindexResponse,
    SearchHit,
    SearchRequest,
    SearchResponse,
)
from app.services.knowledge_service import knowledge_service


router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post("/reindex", response_model=ReindexResponse)
async def reindex_knowledge(req: ReindexRequest, tenant_id: str = Depends(get_tenant_id)):
    indexed = await knowledge_service.reindex_document(
        tenant_id=tenant_id,
        doc_id=req.doc_id,
        text=req.text,
        topic=req.topic,
        language=req.language,
        source_uri=req.source_uri,
        metadata=req.metadata,
    )
    return ReindexResponse(
        tenant_id=tenant_id,
        doc_id=req.doc_id,
        chunks_indexed=indexed,
        embedding_model=knowledge_service.embedding_model,
        embedding_dimensions=knowledge_service.embedding_dimensions,
    )


@router.post("/search", response_model=SearchResponse)
async def search_knowledge(req: SearchRequest, tenant_id: str = Depends(get_tenant_id)):
    try:
        hits = await asyncio.wait_for(
            knowledge_service.search(
                tenant_id=tenant_id,
                query=req.query,
                top_k=req.top_k,
                filters=req.filters,
            ),
            timeout=config.RETRIEVAL_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        hits = []
    return SearchResponse(
        tenant_id=tenant_id,
        results=[SearchHit(**hit) for hit in hits],
        embedding_model=knowledge_service.embedding_model,
    )


@router.delete("/documents/{doc_id}")
async def delete_knowledge_document(doc_id: str, tenant_id: str = Depends(get_tenant_id)):
    deleted = await knowledge_service.delete_document(tenant_id=tenant_id, doc_id=doc_id)
    return {"tenant_id": tenant_id, "doc_id": doc_id, "deleted": deleted}


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_knowledge(req: EvaluateRequest, tenant_id: str = Depends(get_tenant_id)):
    results: list[EvaluateCaseResult] = []
    hits = 0

    for case in req.cases:
        try:
            search_hits = await asyncio.wait_for(
                knowledge_service.search(
                    tenant_id=tenant_id,
                    query=case.query,
                    top_k=case.top_k,
                    filters=case.filters,
                ),
                timeout=config.RETRIEVAL_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            search_hits = []
        returned_doc_ids = [str(hit.get("doc_id")) for hit in search_hits]

        rank = None
        for idx, doc_id in enumerate(returned_doc_ids, start=1):
            if doc_id == case.expected_doc_id:
                rank = idx
                break

        case_hit = rank is not None
        if case_hit:
            hits += 1

        results.append(
            EvaluateCaseResult(
                query=case.query,
                expected_doc_id=case.expected_doc_id,
                hit=case_hit,
                rank=rank,
                returned_doc_ids=returned_doc_ids,
            )
        )

    total_cases = len(req.cases)
    hit_rate = (hits / total_cases) if total_cases > 0 else 0.0
    return EvaluateResponse(
        tenant_id=tenant_id,
        total_cases=total_cases,
        hits=hits,
        hit_rate=hit_rate,
        results=results,
    )
