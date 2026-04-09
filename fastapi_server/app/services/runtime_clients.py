from __future__ import annotations

import httpx
from qdrant_client import AsyncQdrantClient

try:
    import redis.asyncio as redis
except Exception:  # pragma: no cover - optional dependency
    redis = None

from app.core import config


class RuntimeClients:
    def __init__(self) -> None:
        self.http: httpx.AsyncClient | None = None
        self.qdrant: AsyncQdrantClient | None = None
        self.redis: object | None = None

    async def startup(self) -> None:
        if self.http is None:
            self.http = httpx.AsyncClient(timeout=config.HTTP_CLIENT_TIMEOUT_SECONDS)
        if self.qdrant is None:
            self.qdrant = AsyncQdrantClient(
                url=config.QDRANT_URL,
                api_key=config.QDRANT_API_KEY,
                timeout=config.QDRANT_TIMEOUT_SECONDS,
            )
        if self.redis is None and redis is not None and config.REDIS_URL:
            try:
                self.redis = redis.from_url(config.REDIS_URL, decode_responses=True)
                await self.redis.ping()
            except Exception:
                self.redis = None

    async def shutdown(self) -> None:
        if self.http is not None:
            await self.http.aclose()
            self.http = None
        if self.qdrant is not None:
            await self.qdrant.close()
            self.qdrant = None
        if self.redis is not None:
            await self.redis.close()
            self.redis = None

    def get_http(self) -> httpx.AsyncClient:
        if self.http is None:
            raise RuntimeError("Runtime HTTP client is not initialized")
        return self.http

    def get_qdrant(self) -> AsyncQdrantClient:
        if self.qdrant is None:
            raise RuntimeError("Runtime Qdrant client is not initialized")
        return self.qdrant

    def get_redis(self) -> object | None:
        return self.redis


runtime_clients = RuntimeClients()
