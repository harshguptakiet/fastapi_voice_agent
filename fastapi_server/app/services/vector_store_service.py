from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from qdrant_client.http import models as qm

from app.core import config
from app.services.runtime_clients import runtime_clients


@dataclass(slots=True)
class VectorRecord:
    vector_id: str
    doc_id: str
    chunk_id: str
    embedding: list[float]
    text: str
    metadata: dict[str, Any]


class InMemoryVectorStore:
    def __init__(self):
        self._store: dict[str, dict[str, dict[str, VectorRecord]]] = defaultdict(lambda: defaultdict(dict))

    async def upsert(self, *, tenant_id: str, namespace: str, record: VectorRecord) -> None:
        self._store[tenant_id][namespace][record.vector_id] = record

    async def delete_document(self, *, tenant_id: str, namespace: str, doc_id: str) -> int:
        records = self._store[tenant_id][namespace]
        to_delete = [rid for rid, value in records.items() if value.doc_id == doc_id]
        for rid in to_delete:
            del records[rid]
        return len(to_delete)

    async def search(
        self,
        *,
        tenant_id: str,
        namespace: str,
        query_embedding: list[float],
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[tuple[VectorRecord, float]]:
        filters = filters or {}
        records = self._store[tenant_id][namespace].values()
        scored: list[tuple[VectorRecord, float]] = []
        for record in records:
            if not self._match_filters(record.metadata, filters):
                continue
            score = self._cosine_similarity(query_embedding, record.embedding)
            if score <= 0:
                continue
            scored.append((record, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[: max(1, top_k)]

    def _match_filters(self, metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
        return all(metadata.get(key) == value for key, value in filters.items())

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)


class QdrantVectorStore:
    def __init__(self) -> None:
        self._collection_prefix = config.QDRANT_COLLECTION_PREFIX
        self._known_collections: set[str] = set()
        self._indexed_collections: set[str] = set()

    def _collection_name(self, tenant_id: str, namespace: str) -> str:
        raw = f"{self._collection_prefix}_{tenant_id}_{namespace}"
        return re.sub(r"[^A-Za-z0-9_-]", "_", raw)[:120]

    def _point_id(self, vector_id: str) -> int:
        digest = hashlib.sha256(vector_id.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)

    async def _ensure_collection(self, collection_name: str, vector_size: int) -> None:
        if collection_name in self._known_collections:
            if collection_name not in self._indexed_collections:
                await self._ensure_payload_indexes(collection_name)
            return

        client = runtime_clients.get_qdrant()
        try:
            await client.get_collection(collection_name)
            self._known_collections.add(collection_name)
            await self._ensure_payload_indexes(collection_name)
            return
        except Exception:
            pass

        try:
            await client.create_collection(
                collection_name=collection_name,
                vectors_config=qm.VectorParams(size=int(vector_size), distance=qm.Distance.COSINE),
            )
        except Exception as exc:
            # Concurrent writers may race to create the same collection.
            if "already exists" not in str(exc).lower():
                raise
        self._known_collections.add(collection_name)
        await self._ensure_payload_indexes(collection_name)

    async def _ensure_payload_indexes(self, collection_name: str) -> None:
        if collection_name in self._indexed_collections:
            return

        client = runtime_clients.get_qdrant()
        for field_name in (
            "doc_id",
            "tenant_id",
            "language",
            "topic",
            "access_level",
            "session_id",
            "role",
            "memory_type",
        ):
            try:
                await client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=qm.PayloadSchemaType.KEYWORD,
                )
            except Exception:
                # Existing index or provider mismatch; safe to continue for compatibility.
                continue
        self._indexed_collections.add(collection_name)

    async def upsert(self, *, tenant_id: str, namespace: str, record: VectorRecord) -> None:
        collection_name = self._collection_name(tenant_id, namespace)
        await self._ensure_collection(collection_name, len(record.embedding))
        point = qm.PointStruct(
            id=self._point_id(record.vector_id),
            vector=record.embedding,
            payload={
                "vector_id": record.vector_id,
                "tenant_id": tenant_id,
                "namespace": namespace,
                "doc_id": record.doc_id,
                "chunk_id": record.chunk_id,
                "text": record.text,
                **record.metadata,
            },
        )
        await runtime_clients.get_qdrant().upsert(collection_name=collection_name, points=[point], wait=False)

    async def delete_document(self, *, tenant_id: str, namespace: str, doc_id: str) -> int:
        collection_name = self._collection_name(tenant_id, namespace)
        await self._ensure_collection(collection_name, max(1, config.EMBEDDING_DIMENSIONS))

        filt = qm.Filter(
            must=[qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id))]
        )
        await runtime_clients.get_qdrant().delete(
            collection_name=collection_name,
            points_selector=qm.FilterSelector(filter=filt),
            wait=True,
        )
        return 1

    async def search(
        self,
        *,
        tenant_id: str,
        namespace: str,
        query_embedding: list[float],
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[tuple[VectorRecord, float]]:
        collection_name = self._collection_name(tenant_id, namespace)
        await self._ensure_collection(collection_name, len(query_embedding))

        must: list[qm.Condition] = []
        for key, value in (filters or {}).items():
            must.append(qm.FieldCondition(key=key, match=qm.MatchValue(value=value)))

        query_filter = qm.Filter(must=must) if must else None
        client = runtime_clients.get_qdrant()
        if hasattr(client, "search"):
            points = await client.search(
                collection_name=collection_name,
                query_vector=query_embedding,
                limit=max(1, top_k),
                query_filter=query_filter,
                with_payload=True,
            )
        else:
            # qdrant-client >= 1.10 uses query_points/query APIs.
            response = await client.query_points(
                collection_name=collection_name,
                query=query_embedding,
                limit=max(1, top_k),
                query_filter=query_filter,
                with_payload=True,
            )
            points = list(getattr(response, "points", []) or [])

        out: list[tuple[VectorRecord, float]] = []
        for point in points:
            payload = dict(point.payload or {})
            score = float(getattr(point, "score", 0.0) or 0.0)
            metadata = dict(payload)
            metadata.pop("vector_id", None)
            metadata.pop("doc_id", None)
            metadata.pop("chunk_id", None)
            text = str(metadata.pop("text", ""))
            out.append(
                (
                    VectorRecord(
                        vector_id=str(payload.get("vector_id") or point.id),
                        doc_id=str(payload.get("doc_id") or ""),
                        chunk_id=str(payload.get("chunk_id") or ""),
                        embedding=[],
                        text=text,
                        metadata=metadata,
                    ),
                    score,
                )
            )
        return out


class VectorStoreAdapter:
    def __init__(self) -> None:
        self._memory = InMemoryVectorStore()
        self._configured_provider = (config.VECTOR_STORE_PROVIDER or "memory").strip().lower() or "memory"
        self._fallback_used = False
        if self._configured_provider == "qdrant":
            self._active: Any = QdrantVectorStore()
        else:
            self._active = self._memory

    @property
    def configured_provider(self) -> str:
        return self._configured_provider

    @property
    def backend_name(self) -> str:
        return self._active.__class__.__name__

    @property
    def fallback_used(self) -> bool:
        return self._fallback_used

    async def upsert(self, *, tenant_id: str, namespace: str, record: VectorRecord) -> None:
        try:
            await self._active.upsert(tenant_id=tenant_id, namespace=namespace, record=record)
        except Exception:
            if config.VECTOR_STORE_FALLBACK_TO_MEMORY and self._active is not self._memory:
                self._fallback_used = True
                self._active = self._memory
                await self._memory.upsert(tenant_id=tenant_id, namespace=namespace, record=record)
                return
            raise

    async def delete_document(self, *, tenant_id: str, namespace: str, doc_id: str) -> int:
        try:
            return int(await self._active.delete_document(tenant_id=tenant_id, namespace=namespace, doc_id=doc_id))
        except Exception:
            if config.VECTOR_STORE_FALLBACK_TO_MEMORY and self._active is not self._memory:
                self._fallback_used = True
                self._active = self._memory
                return int(await self._memory.delete_document(tenant_id=tenant_id, namespace=namespace, doc_id=doc_id))
            raise

    async def search(
        self,
        *,
        tenant_id: str,
        namespace: str,
        query_embedding: list[float],
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[tuple[VectorRecord, float]]:
        try:
            return await self._active.search(
                tenant_id=tenant_id,
                namespace=namespace,
                query_embedding=query_embedding,
                top_k=top_k,
                filters=filters,
            )
        except Exception:
            if config.VECTOR_STORE_FALLBACK_TO_MEMORY and self._active is not self._memory:
                self._fallback_used = True
                self._active = self._memory
                return await self._memory.search(
                    tenant_id=tenant_id,
                    namespace=namespace,
                    query_embedding=query_embedding,
                    top_k=top_k,
                    filters=filters,
                )
            raise


vector_store = VectorStoreAdapter()
