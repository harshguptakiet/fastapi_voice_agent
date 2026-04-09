from __future__ import annotations

import re
from typing import Any


class MetadataEnrichmentService:
    """Infer lightweight metadata for retrieval filters and attribution."""

    _TOPIC_KEYWORDS: dict[str, set[str]] = {
        "billing": {"invoice", "refund", "payment", "pricing", "subscription", "charge"},
        "support": {"ticket", "issue", "help", "support", "troubleshoot"},
        "hr": {"leave", "vacation", "policy", "manager", "employee"},
        "product": {"feature", "release", "roadmap", "version", "api"},
        "education": {"student", "lesson", "course", "quiz", "learning"},
    }

    def enrich(
        self,
        *,
        text: str,
        source_uri: str | None,
        topic: str | None,
        language: str | None,
        extra_metadata: dict[str, Any] | None,
        section_title: str | None,
    ) -> dict[str, Any]:
        language_value = self._normalize_language(language) or self._detect_language(text)
        topic_value = (topic or "").strip().lower() or self._infer_topic(text)

        metadata: dict[str, Any] = {
            "language": language_value,
            "topic": topic_value,
            "source_uri": source_uri,
            "source_type": self._source_type(source_uri),
            "section_title": section_title,
            "char_count": len(text),
            "word_count": len(re.findall(r"\w+", text)),
        }

        if extra_metadata:
            metadata.update(extra_metadata)

        return metadata

    def _normalize_language(self, language: str | None) -> str:
        raw = (language or "").strip().lower()
        if not raw:
            return ""
        # Keep retrieval filters stable across values like en-US/en_IN/en.
        primary = raw.replace("_", "-").split("-", 1)[0].strip()
        return primary or raw

    def _source_type(self, source_uri: str | None) -> str:
        if not source_uri:
            return "unknown"
        lowered = source_uri.lower()
        if lowered.endswith(".pdf"):
            return "pdf"
        if lowered.endswith(".docx"):
            return "docx"
        if lowered.endswith(".pptx"):
            return "pptx"
        if "transcript" in lowered:
            return "transcript"
        return "text"

    def _detect_language(self, text: str) -> str:
        if not text:
            return "en"
        # Lightweight heuristic; upgrade path is langdetect/fasttext later.
        ascii_ratio = sum(1 for c in text if ord(c) < 128) / max(1, len(text))
        return "en" if ascii_ratio > 0.85 else "unknown"

    def _infer_topic(self, text: str) -> str:
        terms = set(re.findall(r"\w+", text.lower()))
        best_topic = "general"
        best_score = 0

        for topic, keywords in self._TOPIC_KEYWORDS.items():
            score = len(terms & keywords)
            if score > best_score:
                best_score = score
                best_topic = topic

        return best_topic


metadata_enrichment_service = MetadataEnrichmentService()
