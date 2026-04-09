from __future__ import annotations

import uuid
from typing import Any

from app.services.embedding_service import embedding_service
from app.services.knowledge_repository import knowledge_repository
from app.services.metadata_enrichment_service import metadata_enrichment_service
from app.services.retrieval_cache_service import retrieval_cache_service
from app.services.text_chunking_service import text_chunking_service
from app.services.vector_store_service import VectorRecord, vector_store


class KnowledgeService:
    def __init__(self) -> None:
        self._namespace = "knowledge-v1"
        self._indexed_documents_total = 0
        self._indexed_chunks_total = 0
        self._search_queries_total = 0
        self._search_hits_total = 0

    @property
    def embedding_model(self) -> str:
        return embedding_service.model_name

    @property
    def embedding_dimensions(self) -> int:
        return embedding_service.dimensions

    async def reindex_document(
        self,
        tenant_id: str,
        doc_id: str,
        text: str,
        topic: str | None = None,
        language: str = "en",
        source_uri: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        metadata = metadata or {}
        await vector_store.delete_document(
            tenant_id=tenant_id,
            namespace=self._namespace,
            doc_id=doc_id,
        )

        chunk_candidates = text_chunking_service.chunk(text)
        if not chunk_candidates:
            return 0

        rows_to_persist: list[dict[str, Any]] = []
        for idx, chunk in enumerate(chunk_candidates, start=1):
            chunk_id = f"chk_{uuid.uuid4().hex[:10]}"
            embedding = await embedding_service.embed_text_async(chunk.text)
            enriched = metadata_enrichment_service.enrich(
                text=chunk.text,
                source_uri=source_uri,
                topic=topic,
                language=language,
                extra_metadata=metadata,
                section_title=chunk.section_title,
            )
            enriched.update(
                {
                    "tenant_id": tenant_id,
                    "doc_id": doc_id,
                    "chunk_id": chunk_id,
                    "source_identifier": f"{doc_id}#{idx}",
                    "source_id": f"{doc_id}#{idx}",
                    "document_name": metadata.get("document_name") or doc_id,
                    "document_version": metadata.get("document_version") or "v1",
                    "timestamp": metadata.get("timestamp"),
                    "embedding_model": self.embedding_model,
                    "embedding_dimensions": self.embedding_dimensions,
                }
            )

            await vector_store.upsert(
                tenant_id=tenant_id,
                namespace=self._namespace,
                record=VectorRecord(
                    vector_id=f"{doc_id}:{chunk_id}",
                    doc_id=doc_id,
                    chunk_id=chunk_id,
                    embedding=embedding,
                    text=chunk.text,
                    metadata=enriched,
                ),
            )

            rows_to_persist.append(
                {
                    "chunk_id": chunk_id,
                    "source_identifier": enriched.get("source_identifier"),
                    "text": chunk.text,
                    "embedding": embedding,
                    "metadata": enriched,
                }
            )

        knowledge_repository.replace_document_chunks(
            tenant_id=tenant_id,
            doc_id=doc_id,
            rows=rows_to_persist,
        )

        self._indexed_documents_total += 1
        self._indexed_chunks_total += len(chunk_candidates)
        return len(chunk_candidates)

    async def search(
        self,
        tenant_id: str,
        query: str,
        top_k: int,
        filters: dict[str, Any],
        use_cache: bool = True,
        query_embedding: list[float] | None = None,
        return_cache_hit: bool = False,
    ) -> list[dict[str, Any]] | tuple[list[dict[str, Any]], bool]:
        self._search_queries_total += 1
        cache_key = retrieval_cache_service.make_key(
            tenant_id,
            query,
            filters,
            access_level=(filters or {}).get("access_level"),
            language=(filters or {}).get("language"),
            top_k=top_k,
        )
        if use_cache:
            cached = await retrieval_cache_service.get_json(cache_key)
            if isinstance(cached, list):
                self._search_hits_total += len(cached)
                if return_cache_hit:
                    return cached, True
                return cached

        embedding = query_embedding
        if embedding is None:
            embedding = await embedding_service.embed_text_async(query)
        results = await vector_store.search(
            tenant_id=tenant_id,
            namespace=self._namespace,
            query_embedding=embedding,
            top_k=top_k,
            filters=filters,
        )

        hits: list[dict[str, Any]] = []
        for record, score in results:
            hits.append(
                {
                    "chunk_id": record.chunk_id,
                    "doc_id": record.doc_id,
                    "score": float(score),
                    "text": record.text[:600],
                    "metadata": record.metadata,
                }
            )

        self._search_hits_total += len(hits)
        if use_cache:
            await retrieval_cache_service.set_json(cache_key, hits)
        if return_cache_hit:
            return hits, False
        return hits

    async def delete_document(self, tenant_id: str, doc_id: str) -> bool:
        deleted = await vector_store.delete_document(
            tenant_id=tenant_id,
            namespace=self._namespace,
            doc_id=doc_id,
        )
        knowledge_repository.delete_document(tenant_id=tenant_id, doc_id=doc_id)
        return deleted > 0

    def get_metrics_snapshot(self) -> dict[str, int]:
        return {
            "indexed_documents_total": self._indexed_documents_total,
            "indexed_chunks_total": self._indexed_chunks_total,
            "search_queries_total": self._search_queries_total,
            "search_hits_total": self._search_hits_total,
            "persisted_chunks": knowledge_repository.count_chunks(),
        }


knowledge_service = KnowledgeService()
