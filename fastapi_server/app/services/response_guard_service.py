from __future__ import annotations

import re

_TRAILING_CONJUNCTION_RE = re.compile(r"\b(and|so|but|because|which|that|or)\W*$", flags=re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


class ResponseGuardService:
    """Applies speech-safe formatting constraints before TTS synthesis."""

    def enforce(self, text: str, *, max_sentences: int = 2, max_words: int = 30) -> str:
        raw = (text or "").strip()
        if not raw:
            return "I do not have enough information right now."

        cleaned = self._strip_disallowed_formatting(raw)
        cleaned = self._normalize_whitespace(cleaned)

        sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(cleaned) if s.strip()]
        if sentences:
            cleaned = " ".join(sentences[:max_sentences])

        words = cleaned.split()
        if len(words) > max_words:
            cleaned = " ".join(words[:max_words]).rstrip(" ,;:-")

        cleaned = _TRAILING_CONJUNCTION_RE.sub("", cleaned).strip()
        if cleaned and cleaned[-1] not in ".!?":
            cleaned += "."

        return cleaned or "I do not have enough information right now."

    def _strip_disallowed_formatting(self, text: str) -> str:
        lines = text.splitlines()
        normalized: list[str] = []
        for line in lines:
            item = line.strip()
            if not item:
                continue
            # Remove markdown bullets and numbered prefixes.
            item = re.sub(r"^(?:[-*•]+\s+|\d+\.\s+)", "", item)
            item = re.sub(r"^`{1,3}|`{1,3}$", "", item)
            normalized.append(item)
        return " ".join(normalized)

    def _normalize_whitespace(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()


response_guard_service = ResponseGuardService()
