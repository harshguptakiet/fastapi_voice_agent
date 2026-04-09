from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from app.core import config
from app.services.runtime_clients import runtime_clients


class RetrievalCacheService:
    def __init__(self) -> None:
        self._local: dict[str, tuple[float, Any]] = {}

    async def startup(self) -> None:
        # Redis is initialized in shared runtime clients; this is a compatibility no-op.
        return None

    async def shutdown(self) -> None:
        return None

    @property
    def _client(self) -> Any | None:
        return runtime_clients.get_redis()

    def cache_key(self, query: str) -> str:
        digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
        return f"retrieval:{digest}"

    def _stable_filters_hash(self, filters: dict[str, Any] | None) -> str:
        payload = filters or {}
        normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    async def get(self, query: str) -> Any | None:
        key = self.cache_key(query)
        if self._client is not None:
            raw = await self._client.get(key)
            if not raw:
                return None
            return json.loads(raw)

        item = self._local.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at < time.time():
            self._local.pop(key, None)
            return None
        return value

    async def set(self, query: str, docs: Any, ttl_seconds: int | None = None) -> None:
        ttl = ttl_seconds or max(config.RETRIEVAL_CACHE_TTL_SECONDS, 600)
        key = self.cache_key(query)
        if self._client is not None:
            await self._client.setex(key, ttl, json.dumps(docs, ensure_ascii=True))
            return

        self._local[key] = (time.time() + ttl, docs)

    def make_key(
        self,
        tenant_id: str,
        query: str,
        filters: dict[str, Any] | None = None,
        *,
        access_level: str | None = None,
        language: str | None = None,
        top_k: int | None = None,
    ) -> str:
        query_hash = hashlib.sha256((query or "").encode("utf-8")).hexdigest()
        filters_hash = self._stable_filters_hash(filters)
        resolved_access = (access_level or (filters or {}).get("access_level") or "").strip().lower() or "none"
        resolved_language = (language or (filters or {}).get("language") or "").strip().lower() or "none"
        resolved_tenant = (tenant_id or "default").strip() or "default"
        resolved_top_k = max(1, int(top_k or 1))
        return (
            "retrieval:"
            f"{resolved_tenant}:{query_hash}:{filters_hash}:{resolved_access}:{resolved_language}:{resolved_top_k}"
        )

    async def get_json(self, key: str) -> Any | None:
        if self._client is not None:
            raw = await self._client.get(key)
            if raw is None:
                return None
            return json.loads(raw)

        item = self._local.get(key)
        if not item:
            return None
        expires_at, value = item
        if expires_at < time.time():
            self._local.pop(key, None)
            return None
        return value

    async def set_json(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        ttl = ttl_seconds or max(config.RETRIEVAL_CACHE_TTL_SECONDS, 600)
        if self._client is not None:
            await self._client.setex(key, ttl, json.dumps(value, ensure_ascii=True))
            return

        self._local[key] = (time.time() + ttl, value)


retrieval_cache_service = RetrievalCacheService()
