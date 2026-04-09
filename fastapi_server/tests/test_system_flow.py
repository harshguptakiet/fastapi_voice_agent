from __future__ import annotations

import asyncio
import importlib
import os
import unittest


class _StubLLM:
    async def generate_response(self, prompt: str, **_kwargs):
        if "CONTEXT DOCUMENTS" in prompt:
            return "[emotion: calm] Enterprise refunds are processed in seven business days."
        return "[emotion: calm] General guidance answer."

    async def stream_response(self, prompt: str, on_token, **_kwargs):
        text = (
            "Enterprise refunds are processed in seven business days."
            if "CONTEXT DOCUMENTS" in prompt
            else "General guidance answer."
        )
        for token in text.split(" "):
            await on_token(token + " ")
            await asyncio.sleep(0)


class SystemFlowTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["EMBEDDING_PROVIDER"] = "local"
        os.environ["VECTOR_STORE_PROVIDER"] = "memory"
        os.environ["EMBEDDING_FALLBACK_TO_LOCAL"] = "true"
        os.environ["VECTOR_STORE_FALLBACK_TO_MEMORY"] = "true"
        os.environ["SIMILARITY_THRESHOLD"] = "0.35"

        import app.core.config as config_module
        import app.services.embedding_service as embedding_module
        import app.services.vector_store_service as vector_module
        import app.services.knowledge_service as knowledge_module
        import app.services.orchestrator as orchestrator_module
        import app.services.retrieval_cache_service as cache_module

        importlib.reload(config_module)
        importlib.reload(embedding_module)
        importlib.reload(vector_module)
        importlib.reload(cache_module)
        importlib.reload(knowledge_module)
        importlib.reload(orchestrator_module)

        cls.knowledge_service = knowledge_module.knowledge_service
        cls.orchestrator_module = orchestrator_module

    async def test_full_system_flow(self):
        tenant_a = "tenant-system-a"
        tenant_b = "tenant-system-b"

        await self.knowledge_service.reindex_document(
            tenant_id=tenant_a,
            doc_id="billing_doc_a",
            text="Enterprise refunds are processed in seven business days.",
            topic="billing",
            language="en",
            metadata={"document_name": "Billing Policy A", "access_level": "internal"},
        )
        await self.knowledge_service.reindex_document(
            tenant_id=tenant_b,
            doc_id="hr_doc_b",
            text="Vacation requests require manager approval.",
            topic="hr",
            language="en",
            metadata={"document_name": "HR Policy B", "access_level": "internal"},
        )

        hits_a = await self.knowledge_service.search(
            tenant_id=tenant_a,
            query="refund timeline",
            top_k=5,
            filters={"tenant_id": tenant_a, "language": "en"},
            use_cache=False,
        )
        self.assertTrue(all(hit.get("doc_id") != "hr_doc_b" for hit in hits_a))

        interaction = self.orchestrator_module.NormalizedInteractionInput(
            session_id="system-flow-session",
            input_type="text",
            normalized_text="How long do enterprise refunds take?",
            language="en",
        )
        orchestrator = self.orchestrator_module.ConversationOrchestrator(llm_handler=_StubLLM())

        result = await orchestrator.process_interaction_with_attribution(
            interaction,
            tenant_id=tenant_a,
            use_knowledge=True,
            knowledge_top_k=3,
        )
        self.assertIn("response_text", result)
        self.assertIn("fallback_triggered", result)

        unknown_interaction = self.orchestrator_module.NormalizedInteractionInput(
            session_id="system-flow-fallback",
            input_type="text",
            normalized_text="Tell me tomorrow weather in tokyo",
            language="en",
        )
        fallback_result = await orchestrator.process_interaction_with_attribution(
            unknown_interaction,
            tenant_id=tenant_a,
            use_knowledge=True,
            knowledge_top_k=3,
        )
        self.assertIn("fallback_triggered", fallback_result)

        stream_events = []
        async for event in orchestrator.stream_interaction(
            interaction,
            tenant_id=tenant_a,
            use_knowledge=True,
            knowledge_top_k=3,
        ):
            stream_events.append(event)

        self.assertTrue(stream_events, "Streaming should emit events")
        self.assertEqual(stream_events[0].get("event"), "message")
        self.assertEqual(stream_events[-1].get("event"), "done")
        self.assertEqual(stream_events[-1].get("data"), "true")

        metrics_events = [e for e in stream_events if e.get("event") == "metrics"]
        self.assertTrue(metrics_events, "Streaming should emit metrics")


if __name__ == "__main__":
    unittest.main()
