from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
from typing import Any, AsyncGenerator, Optional

from app.core import config
from app.schemas.interaction import NormalizedInteractionInput
from app.services.context_service import context
from app.services.conversation_memory_service import conversation_memory_service
from app.services.embedding_service import embedding_service
from app.services.knowledge_repository import knowledge_repository
from app.services.knowledge_service import knowledge_service
from app.services.llm_handler import LLMHandler
from app.services.logger_service import logger as app_logger
from app.services.retrieval_cache_service import retrieval_cache_service

logger = logging.getLogger(__name__)

VOICE_AGENT_POLICY = (
    "You are a real-time conversational voice assistant. "
    "Your response will be spoken aloud during a live conversation. "
    "Always use complete sentences and never end with an unfinished thought. "
    "Keep responses clear, natural, and concise for speech playback. "
    "Use simple sentence structure and avoid nested clauses, filler, and technical writing style. "
    "Prefer 1 sentence and at most 2 sentences. "
    "Keep total length between 5 and 30 words when possible. "
    "End every response with proper punctuation. "
    "Do not use markdown, bullet points, numbered lists, emojis, or role labels. "
    "Answer the user's request first, then optionally ask one short follow-up question."
)

TEXT_AGENT_POLICY = (
    "You are a helpful conversational assistant. "
    "Respond clearly and directly. "
    "Use concise paragraphs and complete thoughts. "
    "Prefer 1 to 3 short paragraphs depending on question complexity. "
    "Do not use markdown tables unless explicitly asked."
)

GROUNDED_RAG_POLICY = (
    "Answer strictly from provided sources. "
    "If insufficient evidence, answer exactly: I couldn't find relevant information in our documentation."
)

GENERAL_KNOWLEDGE_POLICY = (
    "When no documentation context is provided, answer using your general knowledge. "
    "Do not claim missing documentation unless the user explicitly asks for documentation-only output."
)

MAX_FALLBACK_RETRY_ATTEMPTS = 1
FALLBACK_RETRY_MAX_RESPONSE_CHARS = 120
FALLBACK_RETRY_MAX_LLM_MS = 1200.0


class ConversationOrchestrator:
    def __init__(self, llm_handler: Optional[LLMHandler] = None):
        self.llm_handler = llm_handler or LLMHandler()

    def _is_doc_fallback_text(self, text: str | None) -> bool:
        if not text:
            return False
        return text.strip().lower() == config.FALLBACK_NO_KNOWLEDGE_RESPONSE.strip().lower()

    async def _retry_general_answer(
        self,
        *,
        query: str,
        provider: Optional[str],
        llm_model: Optional[str],
    ) -> str | None:
        retry_prompt = (
            "Answer the user question directly using general world knowledge in one short sentence. "
            "Do not mention documentation, sources, or missing context.\n\n"
            f"Question: {query}\n"
            "Answer:"
        )
        try:
            queue: asyncio.Queue[str | None] = asyncio.Queue()

            async def _on_token(token: str):
                await queue.put(token)

            async def _producer():
                try:
                    await self.llm_handler.stream_response(
                        retry_prompt,
                        provider=provider,
                        llm_model=llm_model,
                        on_token=_on_token,
                    )
                finally:
                    await queue.put(None)

            producer = asyncio.create_task(_producer())
            parts: list[str] = []
            try:
                while True:
                    token = await queue.get()
                    if token is None:
                        break
                    parts.append(token)
            finally:
                if not producer.done():
                    producer.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await producer
            text = "".join(parts)
        except Exception:
            return None
        _, cleaned = self._extract_emotion_and_clean(text)
        cleaned = cleaned.strip()
        if not cleaned or self._is_doc_fallback_text(cleaned):
            return None
        return cleaned

    def _normalize_language(self, language: str | None) -> str:
        raw = (language or "en").strip().lower()
        if not raw:
            return "en"
        primary = raw.replace("_", "-").split("-", 1)[0].strip()
        return primary or "en"

    def _schedule_long_term_write(
        self,
        *,
        tenant_id: str,
        session_id: str,
        role: str,
        content: str,
        language: str,
    ) -> None:
        task = asyncio.create_task(
            conversation_memory_service.append_long_term_message(
                tenant_id=tenant_id,
                session_id=session_id,
                role=role,
                content=content,
                language=language,
            )
        )

        def _log_failure(done_task: asyncio.Task[Any]) -> None:
            try:
                done_task.result()
            except asyncio.CancelledError:
                return
            except Exception:
                logger.warning("Long-term memory write failed", exc_info=True)

        task.add_done_callback(_log_failure)

    def _can_retry_after_fallback(
        self,
        *,
        strict_grounding: bool,
        retry_budget: int,
        interaction: NormalizedInteractionInput,
        response_text: str,
        is_streaming: bool,
        llm_elapsed_ms: float | None = None,
    ) -> bool:
        _ = strict_grounding, is_streaming
        if retry_budget <= 0:
            return False
        if not self._is_doc_fallback_text(response_text):
            return False
        if len((response_text or "").strip()) > FALLBACK_RETRY_MAX_RESPONSE_CHARS:
            return False
        if llm_elapsed_ms is not None and llm_elapsed_ms > FALLBACK_RETRY_MAX_LLM_MS:
            return False
        return True

    async def process_interaction_with_attribution(
        self,
        interaction: NormalizedInteractionInput,
        provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        tenant_id: str = "default",
        access_level: str | None = None,
        use_knowledge: bool = True,
        knowledge_top_k: int = 3,
    ) -> dict[str, Any]:
        total_started = time.perf_counter()
        timings: dict[str, float] = {}
        retry_budget = MAX_FALLBACK_RETRY_ATTEMPTS

        session_id = interaction.session_id
        text = interaction.normalized_text
        language = self._normalize_language(interaction.language)
        if not context.exists(session_id):
            context.set(session_id, {})
        context.update_state(session_id, "language", language)
        await conversation_memory_service.append_short_message(
            tenant_id=tenant_id,
            session_id=session_id,
            role="user",
            content=text,
            language=language,
        )

        retrieval_query = text
        history_task = asyncio.create_task(
            conversation_memory_service.get_recent_messages(
                tenant_id=tenant_id,
                session_id=session_id,
                limit=config.SHORT_TERM_MEMORY_PROMPT_MESSAGES,
            )
        )
        query_embedding_task = asyncio.create_task(embedding_service.embed_text_async(retrieval_query))

        tenant_has_knowledge = False
        if use_knowledge:
            try:
                tenant_has_knowledge = knowledge_repository.count_chunks_for_tenant(tenant_id) > 0
            except Exception:
                # Fail open: if repository probing fails, preserve retrieval behavior.
                tenant_has_knowledge = True

        retrieval_task: asyncio.Task[list[dict[str, Any]]] | None = None
        if use_knowledge and tenant_has_knowledge:
            async def _retrieve_hits() -> list[dict[str, Any]]:
                started = time.perf_counter()
                search_filters: dict[str, Any] = {"tenant_id": tenant_id, "language": language}
                if access_level:
                    search_filters["access_level"] = access_level

                candidate_top_k = min(10, max(5, max(config.RETRIEVAL_CANDIDATE_TOP_K, knowledge_top_k)))
                cache_key = retrieval_cache_service.make_key(
                    tenant_id,
                    retrieval_query,
                    search_filters,
                    access_level=access_level,
                    language=language,
                    top_k=candidate_top_k,
                )
                cached_docs = await retrieval_cache_service.get_json(cache_key)
                if isinstance(cached_docs, list):
                    timings["search_ms"] = round((time.perf_counter() - started) * 1000, 2)
                    return cached_docs

                embedding: list[float] | None = None
                try:
                    embedding = await asyncio.wait_for(
                        asyncio.shield(query_embedding_task),
                        timeout=config.RETRIEVAL_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    timings["search_ms"] = round((time.perf_counter() - started) * 1000, 2)
                    return []
                except Exception:
                    logger.warning("Query embedding failed for retrieval", exc_info=True)

                docs: list[dict[str, Any]] = []
                try:
                    docs = await asyncio.wait_for(
                        knowledge_service.search(
                            tenant_id=tenant_id,
                            query=retrieval_query,
                            top_k=candidate_top_k,
                            filters=search_filters,
                            use_cache=True,
                            query_embedding=embedding,
                        ),
                        timeout=config.RETRIEVAL_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    docs = []
                except Exception:
                    logger.warning("Knowledge retrieval failed; continuing without docs", exc_info=True)
                    docs = []

                if not docs and "language" in search_filters:
                    relaxed_filters = dict(search_filters)
                    relaxed_filters.pop("language", None)
                    relaxed_cache_key = retrieval_cache_service.make_key(
                        tenant_id,
                        retrieval_query,
                        relaxed_filters,
                        access_level=access_level,
                        language=None,
                        top_k=candidate_top_k,
                    )
                    relaxed_cached_docs = await retrieval_cache_service.get_json(relaxed_cache_key)
                    if isinstance(relaxed_cached_docs, list):
                        timings["search_ms"] = round((time.perf_counter() - started) * 1000, 2)
                        return relaxed_cached_docs
                    try:
                        docs = await asyncio.wait_for(
                            knowledge_service.search(
                                tenant_id=tenant_id,
                                query=retrieval_query,
                                top_k=candidate_top_k,
                                filters=relaxed_filters,
                                use_cache=True,
                                query_embedding=embedding,
                            ),
                            timeout=config.RETRIEVAL_TIMEOUT_SECONDS,
                        )
                    except asyncio.TimeoutError:
                        docs = []
                    except Exception:
                        logger.warning("Relaxed-language retrieval failed", exc_info=True)
                        docs = []

                timings["search_ms"] = round((time.perf_counter() - started) * 1000, 2)
                return docs

            retrieval_task = asyncio.create_task(_retrieve_hits())

        async def _recall_memory() -> list[dict[str, Any]]:
            started = time.perf_counter()
            try:
                recent = await asyncio.wait_for(asyncio.shield(history_task), timeout=0.05)
                # On the first turn (or near-empty session), long-term recall is almost always low value.
                if len(recent or []) <= 1:
                    timings["memory_recall_ms"] = round((time.perf_counter() - started) * 1000, 2)
                    return []
            except Exception:
                pass
            embedding: list[float] | None = None
            try:
                embedding = await query_embedding_task
            except Exception:
                logger.warning("Query embedding failed for memory recall", exc_info=True)

            memories: list[dict[str, Any]] = []
            try:
                memories = await asyncio.wait_for(
                    conversation_memory_service.recall_long_term(
                        tenant_id=tenant_id,
                        session_id=session_id,
                        query=retrieval_query,
                        language=language,
                        top_k=config.LONG_TERM_MEMORY_TOP_K,
                        query_embedding=embedding,
                    ),
                    timeout=config.LONG_TERM_MEMORY_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                memories = []
            except Exception:
                logger.warning("Long-term memory recall failed", exc_info=True)
                memories = []

            timings["memory_recall_ms"] = round((time.perf_counter() - started) * 1000, 2)
            return memories

        memory_task = asyncio.create_task(_recall_memory())

        history = await history_task
        if not history:
            history = []

        citations: list[dict[str, Any]] = []
        knowledge_context = ""
        fallback_triggered = False
        retrieval_scores: list[float] = []
        retrieved_chunk_ids: list[str] = []

        if retrieval_task is not None:
            search_hits = await retrieval_task
            llm_top_k = min(config.RETRIEVAL_CONTEXT_TOP_K, max(1, min(config.RETRIEVAL_LLM_TOP_K, knowledge_top_k)))

            retrieval_scores = [float(hit.get("score") or 0.0) for hit in search_hits]
            retrieved_chunk_ids = [str(hit.get("chunk_id") or "") for hit in search_hits]

            top_score = retrieval_scores[0] if retrieval_scores else 0.0
            similarity_threshold = self._resolve_similarity_threshold()
            if not search_hits or top_score < similarity_threshold:
                fallback_triggered = True
            else:
                selected_hits = search_hits[:llm_top_k]
                knowledge_context, citations = self._build_knowledge_context(selected_hits)

        strict_grounding = bool(use_knowledge and knowledge_context)
        memory_hits = await memory_task
        long_term_context = conversation_memory_service.format_long_term_for_prompt(memory_hits)

        if fallback_triggered:
            cleaned_response = config.FALLBACK_NO_KNOWLEDGE_RESPONSE
            emotion = "calm"
            timings["llm_ms"] = 0.0
        else:
            llm_started = time.perf_counter()
            prompt = self._build_prompt(
                history,
                session_id,
                knowledge_context,
                long_term_context=long_term_context,
                strict_grounding=strict_grounding,
                voice_mode=(interaction.input_type == "voice"),
            )
            timings["prompt_ms"] = round((time.perf_counter() - llm_started) * 1000, 2)

            llm_call_started = time.perf_counter()
            try:
                queue: asyncio.Queue[str | None] = asyncio.Queue()

                async def _on_token(token: str):
                    await queue.put(token)

                async def _producer():
                    try:
                        await self.llm_handler.stream_response(
                            prompt,
                            provider=provider,
                            llm_model=llm_model,
                            on_token=_on_token,
                        )
                    finally:
                        await queue.put(None)

                producer = asyncio.create_task(_producer())
                parts: list[str] = []
                try:
                    while True:
                        token = await queue.get()
                        if token is None:
                            break
                        parts.append(token)
                finally:
                    if not producer.done():
                        producer.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await producer

                response_text = "".join(parts)
                emotion, cleaned_response = self._extract_emotion_and_clean(response_text)
                if not cleaned_response.strip():
                    cleaned_response = config.FALLBACK_NO_KNOWLEDGE_RESPONSE
                    emotion = "calm"
                    fallback_triggered = True
            except Exception as exc:
                logger.exception("LLM generation failed", exc_info=exc)
                cleaned_response = config.FALLBACK_NO_KNOWLEDGE_RESPONSE
                emotion = "calm"
                fallback_triggered = True
            timings["llm_ms"] = round((time.perf_counter() - llm_call_started) * 1000, 2)

        if self._can_retry_after_fallback(
            strict_grounding=strict_grounding,
            retry_budget=retry_budget,
            interaction=interaction,
            response_text=cleaned_response,
            is_streaming=False,
            llm_elapsed_ms=timings.get("llm_ms"),
        ):
            retry_budget -= 1
            retry_answer = await self._retry_general_answer(
                query=text,
                provider=provider,
                llm_model=llm_model,
            )
            if retry_answer:
                cleaned_response = retry_answer
                fallback_triggered = False

        context.update_state(session_id, "last_response", cleaned_response)
        context.update_state(session_id, "last_emotion", emotion or "calm")
        if len(text.split()) > 3:
            context.update_state(session_id, "current_topic", text[:30] + "...")
        await conversation_memory_service.append_short_message(
            tenant_id=tenant_id,
            session_id=session_id,
            role="assistant",
            content=cleaned_response,
            language=language,
        )
        self._schedule_long_term_write(
            tenant_id=tenant_id,
            session_id=session_id,
            role="user",
            content=text,
            language=language,
        )
        self._schedule_long_term_write(
            tenant_id=tenant_id,
            session_id=session_id,
            role="assistant",
            content=cleaned_response,
            language=language,
        )

        timings["total_ms"] = round((time.perf_counter() - total_started) * 1000, 2)
        app_logger.event(
            "rag_query",
            {
                "query_text": text,
                "tenant_id": tenant_id,
                "retrieved_chunk_ids": retrieved_chunk_ids,
                "similarity_scores": retrieval_scores,
                "fallback_triggered": fallback_triggered,
                "timings_ms": timings,
            },
        )

        return {
            "response_text": cleaned_response,
            "response_emotion": emotion or "calm",
            "citations": citations,
            "fallback_triggered": fallback_triggered,
            "response_time_ms": timings.get("total_ms"),
            "timings_ms": timings,
        }

    async def stream_interaction(
        self,
        interaction: NormalizedInteractionInput,
        provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        tenant_id: str = "default",
        access_level: str | None = None,
        use_knowledge: bool = True,
        knowledge_top_k: int = 3,
    ) -> AsyncGenerator[dict[str, Any], None]:
        total_started = time.perf_counter()
        timings: dict[str, float] = {}
        cache_hit = False
        token_count = 0
        document_count = 0
        producer: asyncio.Task[None] | None = None
        retry_budget = MAX_FALLBACK_RETRY_ATTEMPTS

        session_id = interaction.session_id
        text = interaction.normalized_text
        language = self._normalize_language(interaction.language)
        if not context.exists(session_id):
            context.set(session_id, {})
        context.update_state(session_id, "language", language)
        await conversation_memory_service.append_short_message(
            tenant_id=tenant_id,
            session_id=session_id,
            role="user",
            content=text,
            language=language,
        )
        history_task = asyncio.create_task(
            conversation_memory_service.get_recent_messages(
                tenant_id=tenant_id,
                session_id=session_id,
                limit=config.SHORT_TERM_MEMORY_PROMPT_MESSAGES,
            )
        )

        retrieval_query = text
        query_embedding_task = asyncio.create_task(embedding_service.embed_text_async(retrieval_query))

        tenant_has_knowledge = False
        if use_knowledge:
            try:
                tenant_has_knowledge = knowledge_repository.count_chunks_for_tenant(tenant_id) > 0
            except Exception:
                tenant_has_knowledge = True

        retrieval_task: asyncio.Task[list[dict[str, Any]]] | None = None
        retrieval_started: float | None = None
        if use_knowledge and tenant_has_knowledge:
            retrieval_started = time.perf_counter()
            async def _retrieve_hits() -> list[dict[str, Any]]:
                nonlocal cache_hit
                search_filters: dict[str, Any] = {"tenant_id": tenant_id, "language": language}
                if access_level:
                    search_filters["access_level"] = access_level

                candidate_top_k = min(10, max(5, max(config.RETRIEVAL_CANDIDATE_TOP_K, knowledge_top_k)))
                cache_key = retrieval_cache_service.make_key(
                    tenant_id,
                    retrieval_query,
                    search_filters,
                    access_level=access_level,
                    language=language,
                    top_k=candidate_top_k,
                )
                cached_docs = await retrieval_cache_service.get_json(cache_key)
                if isinstance(cached_docs, list):
                    cache_hit = True
                    return cached_docs

                embedding: list[float] | None = None
                try:
                    embedding = await asyncio.wait_for(
                        asyncio.shield(query_embedding_task),
                        timeout=config.RETRIEVAL_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    return []
                except Exception:
                    logger.warning("Query embedding failed for retrieval", exc_info=True)

                docs: list[dict[str, Any]] = []
                cache_used = False
                try:
                    result = await asyncio.wait_for(
                        knowledge_service.search(
                            tenant_id=tenant_id,
                            query=retrieval_query,
                            top_k=candidate_top_k,
                            filters=search_filters,
                            use_cache=True,
                            query_embedding=embedding,
                            return_cache_hit=True,
                        ),
                        timeout=config.RETRIEVAL_TIMEOUT_SECONDS,
                    )
                    docs, cache_used = result
                except asyncio.TimeoutError:
                    docs = []
                except Exception:
                    logger.warning("Knowledge retrieval failed during stream; continuing without docs", exc_info=True)
                    docs = []

                if not docs and "language" in search_filters:
                    relaxed_filters = dict(search_filters)
                    relaxed_filters.pop("language", None)
                    relaxed_cache_key = retrieval_cache_service.make_key(
                        tenant_id,
                        retrieval_query,
                        relaxed_filters,
                        access_level=access_level,
                        language=None,
                        top_k=candidate_top_k,
                    )
                    relaxed_cached_docs = await retrieval_cache_service.get_json(relaxed_cache_key)
                    if isinstance(relaxed_cached_docs, list):
                        cache_hit = True
                        return relaxed_cached_docs
                    try:
                        result = await asyncio.wait_for(
                            knowledge_service.search(
                                tenant_id=tenant_id,
                                query=retrieval_query,
                                top_k=candidate_top_k,
                                filters=relaxed_filters,
                                use_cache=True,
                                query_embedding=embedding,
                                return_cache_hit=True,
                            ),
                            timeout=config.RETRIEVAL_TIMEOUT_SECONDS,
                        )
                        docs, cache_used = result
                    except asyncio.TimeoutError:
                        docs = []
                    except Exception:
                        logger.warning("Relaxed-language retrieval failed during stream", exc_info=True)
                        docs = []

                cache_hit = cache_used

                return docs

            retrieval_task = asyncio.create_task(_retrieve_hits())

        async def _recall_memory() -> list[dict[str, Any]]:
            started = time.perf_counter()
            try:
                recent = await asyncio.wait_for(asyncio.shield(history_task), timeout=0.05)
                if len(recent or []) <= 1:
                    timings["memory_recall_ms"] = round((time.perf_counter() - started) * 1000, 2)
                    return []
            except Exception:
                pass
            embedding: list[float] | None = None
            try:
                embedding = await query_embedding_task
            except Exception:
                logger.warning("Query embedding failed for memory recall", exc_info=True)

            memories: list[dict[str, Any]] = []
            try:
                memories = await asyncio.wait_for(
                    conversation_memory_service.recall_long_term(
                        tenant_id=tenant_id,
                        session_id=session_id,
                        query=retrieval_query,
                        language=language,
                        top_k=config.LONG_TERM_MEMORY_TOP_K,
                        query_embedding=embedding,
                    ),
                    timeout=config.LONG_TERM_MEMORY_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                memories = []
            except Exception:
                logger.warning("Long-term memory recall failed", exc_info=True)
                memories = []
            timings["memory_recall_ms"] = round((time.perf_counter() - started) * 1000, 2)
            return memories

        memory_task = asyncio.create_task(_recall_memory())

        try:
            # Flush a neutral first chunk immediately for low perceived latency.
            yield {"event": "message", "data": "Analyzing your question..."}
            timings["first_token_ms"] = round((time.perf_counter() - total_started) * 1000, 2)

            history = await history_task
            if not history:
                history = []

            citations: list[dict[str, Any]] = []
            knowledge_context = ""
            retrieval_scores: list[float] = []
            retrieved_chunk_ids: list[str] = []

            if retrieval_task is not None:
                try:
                    search_hits = await retrieval_task
                except Exception:
                    logger.warning("Knowledge retrieval failed during stream; continuing without docs", exc_info=True)
                    search_hits = []
                if retrieval_started is not None:
                    timings["retrieval_ms"] = round((time.perf_counter() - retrieval_started) * 1000, 2)

                retrieval_scores = [float(hit.get("score") or 0.0) for hit in search_hits]
                retrieved_chunk_ids = [str(hit.get("chunk_id") or "") for hit in search_hits]
                document_count = len(search_hits)
                top_score = retrieval_scores[0] if retrieval_scores else 0.0
                similarity_threshold = self._resolve_similarity_threshold()

                if search_hits and top_score >= similarity_threshold:
                    llm_top_k = min(
                        4,
                        config.RETRIEVAL_CONTEXT_TOP_K,
                        max(1, min(config.RETRIEVAL_LLM_TOP_K, knowledge_top_k)),
                    )
                    selected_hits = search_hits[:llm_top_k]
                    knowledge_context, citations = self._build_knowledge_context(selected_hits)

            strict_grounding = bool(use_knowledge and knowledge_context)
            memory_hits = await memory_task
            long_term_context = conversation_memory_service.format_long_term_for_prompt(memory_hits)

            prompt = self._build_stream_prompt(
                text,
                history,
                knowledge_context,
                long_term_context=long_term_context,
                strict_grounding=strict_grounding,
                voice_mode=(interaction.input_type == "voice"),
            )
            llm_started = time.perf_counter()
            response_parts: list[str] = []
            queue: asyncio.Queue[str | None] = asyncio.Queue()

            async def _on_token(token: str):
                await queue.put(token)

            async def _producer():
                try:
                    await self.llm_handler.stream_response(
                        prompt,
                        provider=provider,
                        llm_model=llm_model,
                        on_token=_on_token,
                    )
                finally:
                    await queue.put(None)

            producer = asyncio.create_task(_producer())
            token_buffer: list[str] = []
            buffer_limit = 8

            try:
                while True:
                    token = await queue.get()
                    if token is None:
                        break
                    logger.debug("LLM token chunk: %s", token)
                    token_count += 1
                    response_parts.append(token)
                    token_buffer.append(token)
                    if len(token_buffer) >= buffer_limit:
                        yield {"event": "token", "data": "".join(token_buffer)}
                        token_buffer.clear()

                if token_buffer:
                    yield {"event": "token", "data": "".join(token_buffer)}
                    token_buffer.clear()
            finally:
                if producer is not None and not producer.done():
                    producer.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await producer

            timings["llm_total_ms"] = round((time.perf_counter() - llm_started) * 1000, 2)
            response_text = "".join(response_parts).strip()
            emotion, cleaned_response = self._extract_emotion_and_clean(response_text)
            fallback_triggered = False
            if not cleaned_response:
                cleaned_response = config.FALLBACK_NO_KNOWLEDGE_RESPONSE
                emotion = "calm"
                fallback_triggered = True
            token_count = max(token_count, len(re.findall(r"\w+", cleaned_response)))

            if self._can_retry_after_fallback(
                strict_grounding=strict_grounding,
                retry_budget=retry_budget,
                interaction=interaction,
                response_text=cleaned_response,
                is_streaming=True,
                llm_elapsed_ms=timings.get("llm_total_ms"),
            ):
                retry_budget -= 1
                retry_answer = await self._retry_general_answer(
                    query=text,
                    provider=provider,
                    llm_model=llm_model,
                )
                if retry_answer:
                    cleaned_response = retry_answer
                    fallback_triggered = False

            context.update_state(session_id, "last_response", cleaned_response)
            context.update_state(session_id, "last_emotion", emotion or "calm")
            if len(text.split()) > 3:
                context.update_state(session_id, "current_topic", text[:30] + "...")
            await conversation_memory_service.append_short_message(
                tenant_id=tenant_id,
                session_id=session_id,
                role="assistant",
                content=cleaned_response,
                language=language,
            )
            self._schedule_long_term_write(
                tenant_id=tenant_id,
                session_id=session_id,
                role="user",
                content=text,
                language=language,
            )
            self._schedule_long_term_write(
                tenant_id=tenant_id,
                session_id=session_id,
                role="assistant",
                content=cleaned_response,
                language=language,
            )

            timings["total_ms"] = round((time.perf_counter() - total_started) * 1000, 2)
            app_logger.event(
                "rag_stream_query",
                {
                    "query_text": text,
                    "tenant_id": tenant_id,
                    "retrieved_chunk_ids": retrieved_chunk_ids,
                    "similarity_scores": retrieval_scores,
                    "fallback_triggered": fallback_triggered,
                    "timings_ms": timings,
                },
            )
            logger.info(
                "rag_stream_metrics",
                extra={
                    "retrieval_ms": timings.get("retrieval_ms", 0.0),
                    "first_token_ms": timings.get("first_token_ms", 0.0),
                    "llm_total_ms": timings.get("llm_total_ms", 0.0),
                    "total_ms": timings.get("total_ms", 0.0),
                    "cache_hit": cache_hit,
                    "token_count": token_count,
                    "document_count": document_count,
                },
            )

            # Authoritative final response after post-processing/retry logic.
            yield {"event": "final_text", "data": cleaned_response}

            yield {
                "event": "metrics",
                "data": json.dumps(
                    {
                        **timings,
                        "cache_hit": cache_hit,
                        "token_count": token_count,
                        "document_count": document_count,
                    },
                    ensure_ascii=True,
                ),
            }
            yield {"event": "done", "data": "true"}

        except asyncio.CancelledError:
            if history_task is not None and not history_task.done():
                history_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await history_task
            if query_embedding_task is not None and not query_embedding_task.done():
                query_embedding_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await query_embedding_task
            if memory_task is not None and not memory_task.done():
                memory_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await memory_task
            if retrieval_task is not None and not retrieval_task.done():
                retrieval_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await retrieval_task
            if producer is not None and not producer.done():
                producer.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await producer
            logger.info("Streaming interaction cancelled by client", extra={"session_id": session_id})
            raise

    def _build_stream_prompt(
        self,
        query: str,
        history: list[dict[str, Any]],
        knowledge_context: str,
        long_term_context: str = "",
        *,
        strict_grounding: bool,
        voice_mode: bool,
    ) -> str:
        if knowledge_context:
            context_block = (
                "CONTEXT DOCUMENTS\n\n"
                f"{knowledge_context}\n\n"
                "Use the context documents when answering. If the answer is not present in the context, "
                "say the information was not found.\n\n"
            )
        else:
            context_block = ""

        memory_block = ""
        if long_term_context:
            memory_block = (
                "PRIOR CONVERSATION MEMORY\n\n"
                f"{long_term_context}\n\n"
                "Use these memory snippets to maintain continuity, but prioritize the user's latest request.\n\n"
            )

        history_block = ""
        recent_turns = history[-6:] if history else []
        if recent_turns:
            lines: list[str] = []
            for item in recent_turns:
                role = str(item.get("role") or "user").strip().lower()
                content = str(item.get("content") or "").strip()
                if not content:
                    continue
                # Avoid repeating the current user message twice in the prompt.
                if role == "user" and content == query:
                    continue
                lines.append(f"{role.capitalize()}: {content}")
            if lines:
                history_block = (
                    "RECENT CHAT CONTEXT\n\n"
                    f"{'\n'.join(lines)}\n\n"
                    "Use this to resolve follow-up references like pronouns and ellipsis.\n\n"
                )

        system_prompt = VOICE_AGENT_POLICY if voice_mode else TEXT_AGENT_POLICY
        if strict_grounding:
            system_prompt = f"{system_prompt} {GROUNDED_RAG_POLICY}"
        else:
            system_prompt = f"{system_prompt} {GENERAL_KNOWLEDGE_POLICY}"

        return (
            f"SYSTEM: {system_prompt}\n\n"
            f"{context_block}"
            f"{memory_block}"
            f"{history_block}"
            f"USER QUESTION:\n{query}\n\n"
            "ANSWER:"
        )

    def get_last_emotion(self, session_id: str) -> str:
        sess = context.get(session_id) or {}
        emotion = sess.get("last_emotion")
        if isinstance(emotion, str) and emotion.strip():
            return emotion.strip().lower()
        return "calm"

    def _build_prompt(
        self,
        history: list[dict[str, Any]],
        session_id: str,
        knowledge_context: str = "",
        long_term_context: str = "",
        *,
        strict_grounding: bool,
        voice_mode: bool,
    ) -> str:
        sess = context.get(session_id) or {}
        persona = sess.get("persona", "default")
        grounding_clause = f" {GROUNDED_RAG_POLICY}" if strict_grounding else f" {GENERAL_KNOWLEDGE_POLICY}"
        base_policy = VOICE_AGENT_POLICY if voice_mode else TEXT_AGENT_POLICY
        system_prompt = f"{base_policy} Persona: {persona}.{grounding_clause}"
        full_prompt = system_prompt + "\n\n"

        if knowledge_context:
            full_prompt += f"Sources:\n{knowledge_context}\n\n"

        if long_term_context:
            full_prompt += f"Prior Conversation Memory:\n{long_term_context}\n\n"

        for msg in history[-4:]:
            full_prompt += f"{msg['role'].capitalize()}: {msg['content']}\n"
        full_prompt += "Assistant:"
        return full_prompt

    def _extract_emotion_and_clean(self, text: str) -> tuple[str | None, str]:
        if not isinstance(text, str):
            return (None, "")
        raw = text.strip()
        m = re.match(r"^\[emotion:\s*([a-zA-Z-]+)\]\s*", raw, flags=re.IGNORECASE)
        if not m:
            return (None, raw)
        emotion = m.group(1).strip().lower()
        cleaned = raw[m.end():].strip()
        return (emotion, cleaned)

    def _build_knowledge_context(self, hits: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
        if not hits:
            return "", []

        snippets: list[str] = []
        citations: list[dict[str, Any]] = []
        for idx, hit in enumerate(hits, start=1):
            metadata = hit.get("metadata") or {}
            quote = (hit.get("text") or hit.get("quote") or "").strip()
            quote = quote[: min(1000, config.RETRIEVAL_CHUNK_CHAR_LIMIT)]
            if quote:
                snippets.append(f"[{idx}]\n{quote}")

            citations.append(
                {
                    "index": idx,
                    "doc_id": hit.get("doc_id"),
                    "chunk_id": hit.get("chunk_id"),
                    "score": hit.get("score"),
                    "document_name": metadata.get("document_name") or hit.get("doc_id"),
                    "section_title": metadata.get("section_title"),
                    "source_uri": metadata.get("source_uri"),
                    "quote": quote,
                }
            )

        return "\n".join(snippets), citations

    def _build_retrieval_query(self, text: str, history: list[dict[str, Any]]) -> str:
        context_turns = history[-3:-1] if len(history) >= 2 else history[-2:]
        formatted_turns: list[str] = []
        for item in context_turns:
            role = str(item.get("role") or "user").lower()
            content = str(item.get("content") or "").strip()
            if content:
                formatted_turns.append(f"{role}: {content}")
        if not formatted_turns:
            return text
        return "\n".join(formatted_turns + [f"user: {text}"])

    def _resolve_similarity_threshold(self) -> float:
        base = float(config.SIMILARITY_THRESHOLD)
        provider = (knowledge_service.embedding_model or "").lower()
        if "local" in provider:
            return min(base, 0.35)
        if "gemini" in provider:
            return min(base, 0.65)
        return base


orchestrator = ConversationOrchestrator()
