from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from app.core import config
from app.services.embedding_service import embedding_service
from app.services.runtime_clients import runtime_clients
from app.services.vector_store_service import VectorRecord, vector_store

logger = logging.getLogger(__name__)


class ConversationMemoryService:
    """Redis short-term memory + Qdrant long-term vector memory for chat context."""

    def __init__(self) -> None:
        self._local_short: dict[str, list[dict[str, Any]]] = {}
        self._short_limit = max(2, config.SHORT_TERM_MEMORY_MAX_MESSAGES)
        self._short_ttl_seconds = max(60, config.SHORT_TERM_MEMORY_TTL_SECONDS)
        self._prompt_limit = max(2, config.SHORT_TERM_MEMORY_PROMPT_MESSAGES)
        self._ltm_top_k = max(1, config.LONG_TERM_MEMORY_TOP_K)
        self._ltm_text_limit = max(120, config.LONG_TERM_MEMORY_MAX_TEXT_CHARS)
        self._namespace = config.LONG_TERM_MEMORY_NAMESPACE.strip() or "conversation-memory-v1"
        # Reuse the shared adapter so we can fall back to in-memory storage when Qdrant is unavailable.
        self._vector_store = vector_store

    def _short_key(self, *, tenant_id: str, session_id: str) -> str:
        return f"chat:memory:short:{tenant_id}:{session_id}"

    @property
    def _redis(self) -> Any | None:
        return runtime_clients.get_redis()

    async def append_short_message(
        self,
        *,
        tenant_id: str,
        session_id: str,
        role: str,
        content: str,
        language: str,
    ) -> None:
        cleaned = (content or "").strip()
        if not cleaned:
            return

        message = {
            "role": (role or "user").strip().lower() or "user",
            "content": cleaned,
            "language": (language or "en").strip().lower() or "en",
            "ts": int(time.time()),
        }
        key = self._short_key(tenant_id=tenant_id, session_id=session_id)
        redis_client = self._redis

        if redis_client is not None:
            try:
                await redis_client.lpush(key, json.dumps(message, ensure_ascii=True))
                await redis_client.ltrim(key, 0, self._short_limit - 1)
                await redis_client.expire(key, self._short_ttl_seconds)
                return
            except Exception:
                logger.warning("Redis short-term memory write failed; using local fallback", exc_info=True)

        rows = self._local_short.get(key, [])
        rows.insert(0, message)
        self._local_short[key] = rows[: self._short_limit]

    async def get_recent_messages(
        self,
        *,
        tenant_id: str,
        session_id: str,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        max_items = max(1, min(limit or self._prompt_limit, self._short_limit))
        key = self._short_key(tenant_id=tenant_id, session_id=session_id)
        redis_client = self._redis
        messages: list[dict[str, Any]] = []

        if redis_client is not None:
            try:
                raw_items = await redis_client.lrange(key, 0, max_items - 1)
                for raw in raw_items:
                    try:
                        item = json.loads(raw)
                    except Exception:
                        continue
                    role = str(item.get("role") or "user")
                    content = str(item.get("content") or "").strip()
                    if content:
                        messages.append({"role": role, "content": content, "timestamp": item.get("ts")})
                # Redis list is newest-first because of LPUSH; convert to chronological order.
                messages.reverse()
                return messages
            except Exception:
                logger.warning("Redis short-term memory read failed; using local fallback", exc_info=True)

        local_items = list(self._local_short.get(key, []))[:max_items]
        local_items.reverse()
        for item in local_items:
            role = str(item.get("role") or "user")
            content = str(item.get("content") or "").strip()
            if content:
                messages.append({"role": role, "content": content, "timestamp": item.get("ts")})
        return messages

    async def append_long_term_message(
        self,
        *,
        tenant_id: str,
        session_id: str,
        role: str,
        content: str,
        language: str,
    ) -> None:
        cleaned = (content or "").strip()
        if len(cleaned) < 3:
            return

        clipped = cleaned[: self._ltm_text_limit]
        embedding = await embedding_service.embed_text_async(clipped)
        ts = int(time.time())
        record = VectorRecord(
            vector_id=f"{session_id}:{ts}:{uuid.uuid4().hex[:10]}",
            doc_id=f"session:{session_id}",
            chunk_id=f"turn:{uuid.uuid4().hex[:10]}",
            embedding=embedding,
            text=clipped,
            metadata={
                "tenant_id": tenant_id,
                "session_id": session_id,
                "role": (role or "user").strip().lower() or "user",
                "language": (language or "en").strip().lower() or "en",
                "memory_type": "conversation",
                "created_at": ts,
            },
        )

        await self._vector_store.upsert(
            tenant_id=tenant_id,
            namespace=self._namespace,
            record=record,
        )

    async def recall_long_term(
        self,
        *,
        tenant_id: str,
        session_id: str,
        query: str,
        language: str,
        top_k: int | None = None,
        query_embedding: list[float] | None = None,
    ) -> list[dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []

        embedding = query_embedding
        if embedding is None:
            embedding = await embedding_service.embed_text_async(q[: self._ltm_text_limit])
        hits = await self._vector_store.search(
            tenant_id=tenant_id,
            namespace=self._namespace,
            query_embedding=embedding,
            top_k=max(1, top_k or self._ltm_top_k),
            filters={
                "tenant_id": tenant_id,
                "session_id": session_id,
                "memory_type": "conversation",
                "language": (language or "en").strip().lower() or "en",
            },
        )

        out: list[dict[str, Any]] = []
        for record, score in hits:
            text = (record.text or "").strip()
            if not text:
                continue
            out.append(
                {
                    "text": text,
                    "score": float(score),
                    "role": str((record.metadata or {}).get("role") or "unknown"),
                    "created_at": (record.metadata or {}).get("created_at"),
                }
            )
        return out

    def format_long_term_for_prompt(self, memories: list[dict[str, Any]]) -> str:
        if not memories:
            return ""

        lines: list[str] = []
        seen: set[str] = set()
        for idx, item in enumerate(memories, start=1):
            text = str(item.get("text") or "").strip()
            role = str(item.get("role") or "memory")
            if not text:
                continue
            if text in seen:
                continue
            seen.add(text)
            lines.append(f"[M{idx}] ({role}) {text}")
        return "\n".join(lines)


conversation_memory_service = ConversationMemoryService()
