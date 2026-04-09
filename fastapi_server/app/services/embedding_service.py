from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import re
from typing import Protocol

from app.core import config
from app.services.runtime_clients import runtime_clients

try:
    from sentence_transformers import SentenceTransformer
except Exception:  # pragma: no cover - optional at runtime
    SentenceTransformer = None


class EmbeddingBackend(Protocol):
    model_name: str
    dimensions: int

    async def embed_text(self, text: str) -> list[float]:
        ...


class LocalHashEmbeddingBackend:
    def __init__(self, model_name: str = "local-hash-v1", dimensions: int = 256):
        self.model_name = model_name
        self.dimensions = max(64, dimensions)

    async def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        terms = re.findall(r"\w+", (text or "").lower())
        if not terms:
            return vector

        for term in terms:
            digest = hashlib.sha256(term.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            weight = 1.0 + ((digest[5] % 7) / 10.0)
            vector[index] += sign * weight

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class LocalBGEEmbeddingBackend:
    _executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="embedding-bge")

    def __init__(self) -> None:
        if SentenceTransformer is None:
            raise RuntimeError("sentence-transformers is required for local BGE embeddings")
        self.model_name = config.LOCAL_EMBEDDING_MODEL
        self._model = SentenceTransformer(self.model_name)
        self.dimensions = 384

    async def embed_text(self, text: str) -> list[float]:
        loop = asyncio.get_running_loop()

        def _encode() -> list[float]:
            vec = self._model.encode(text, normalize_embeddings=True)
            return [float(v) for v in vec]

        values = await loop.run_in_executor(self._executor, _encode)
        self.dimensions = len(values)
        return values


class OpenAIEmbeddingBackend:
    def __init__(self, model_name: str | None = None) -> None:
        self.model_name = model_name or config.EMBEDDING_MODEL or "text-embedding-3-small"
        self.dimensions = max(64, config.EMBEDDING_DIMENSIONS)

    async def embed_text(self, text: str) -> list[float]:
        if not config.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is required for EMBEDDING_PROVIDER=openai")

        url = f"{config.OPENAI_BASE_URL.rstrip('/')}/embeddings"
        payload = {"model": self.model_name, "input": text}
        headers = {
            "Authorization": f"Bearer {config.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

        client = runtime_clients.get_http()
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(
                f"OpenAI embeddings failed (status={response.status_code}): {response.text}"
            )

        data = response.json()
        embedding = data.get("data", [{}])[0].get("embedding")
        if not isinstance(embedding, list):
            raise RuntimeError("OpenAI embeddings response missing data[0].embedding")

        self.dimensions = len(embedding)
        return [float(value) for value in embedding]


class GeminiEmbeddingBackend:
    def __init__(self, model_name: str | None = None) -> None:
        raw_model = model_name or config.EMBEDDING_MODEL or "gemini-embedding-001"
        self.model_name = self._normalize_model(raw_model)
        self.dimensions = max(64, config.EMBEDDING_DIMENSIONS)

    def _normalize_model(self, model_name: str) -> str:
        key = (model_name or "").strip().lower()
        if key.startswith("google/"):
            return key.split("/", 1)[1]
        return model_name

    async def embed_text(self, text: str) -> list[float]:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is required for EMBEDDING_PROVIDER=gemini")

        url = f"{config.GEMINI_BASE_URL.rstrip('/')}/v1beta/models/{self.model_name}:embedContent"
        params = {"key": config.GEMINI_API_KEY}
        payload = {"content": {"parts": [{"text": text}]}}

        client = runtime_clients.get_http()
        response = await client.post(url, params=params, json=payload)
        if response.status_code >= 400:
            raise RuntimeError(
                f"Gemini embeddings failed (status={response.status_code}): {response.text}"
            )

        data = response.json()
        values = ((data.get("embedding") or {}).get("values"))
        if not isinstance(values, list):
            raise RuntimeError("Gemini embeddings response missing embedding.values")

        self.dimensions = len(values)
        return [float(value) for value in values]


class EmbeddingService:
    def __init__(self) -> None:
        self._local_hash = LocalHashEmbeddingBackend(
            model_name="local-hash-v1",
            dimensions=max(64, config.EMBEDDING_DIMENSIONS),
        )
        self._fallback_used = False
        self._configured_provider = (config.EMBEDDING_PROVIDER or "local-bge").strip().lower() or "local-bge"
        self._backend = self._build_backend()

    @property
    def model_name(self) -> str:
        return self._backend.model_name

    @property
    def dimensions(self) -> int:
        return self._backend.dimensions

    @property
    def configured_provider(self) -> str:
        return self._configured_provider

    @property
    def backend_name(self) -> str:
        return self._backend.__class__.__name__

    @property
    def fallback_used(self) -> bool:
        return self._fallback_used

    def _build_backend(self) -> EmbeddingBackend:
        provider = (config.EMBEDDING_PROVIDER or "local-bge").strip().lower()
        if provider in {"local", "local-hash"}:
            return self._local_hash
        if provider in {"local-bge", "bge"}:
            return LocalBGEEmbeddingBackend()
        if provider in {"openai", "openai-embeddings"}:
            return OpenAIEmbeddingBackend()
        if provider in {"gemini", "google"}:
            return GeminiEmbeddingBackend()
        return self._local_hash

    async def embed_text_async(self, text: str) -> list[float]:
        cache_enabled = bool(config.EMBEDDING_CACHE_ENABLED)
        cache_key = f"embed:{hashlib.sha256((text or '').encode('utf-8')).hexdigest()}"
        redis_client = runtime_clients.get_redis() if cache_enabled else None

        if redis_client is not None:
            try:
                cached = await redis_client.get(cache_key)
                if cached:
                    decoded = json.loads(cached)
                    if isinstance(decoded, list):
                        return [float(value) for value in decoded]
            except Exception:
                # Cache failures should never block the request path.
                pass

        try:
            embedding = await self._backend.embed_text(text)
        except Exception:
            if config.EMBEDDING_FALLBACK_TO_LOCAL and self._backend is not self._local_hash:
                self._backend = self._local_hash
                self._fallback_used = True
                embedding = await self._backend.embed_text(text)
            else:
                raise

        if redis_client is not None:
            try:
                await redis_client.setex(
                    cache_key,
                    max(60, int(config.EMBEDDING_CACHE_TTL_SECONDS)),
                    json.dumps(embedding, ensure_ascii=True),
                )
            except Exception:
                pass

        return embedding


embedding_service = EmbeddingService()
