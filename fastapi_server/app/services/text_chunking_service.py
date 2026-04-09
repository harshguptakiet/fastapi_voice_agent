from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(slots=True)
class ChunkCandidate:
    text: str
    section_title: str | None = None


class TextChunkingService:
    """Chunk text into semantically meaningful windows.

    Strategy:
    1) Split by section-like blocks (double newlines)
    2) Keep heading context when possible
    3) Enforce token-like word windows with overlap
    """

    def __init__(self, target_words: int = 140, overlap_words: int = 28):
        self.target_words = max(40, target_words)
        self.overlap_words = max(0, min(overlap_words, self.target_words // 2))

    def chunk(self, text: str) -> list[ChunkCandidate]:
        normalized = self._normalize(text)
        if not normalized:
            return []

        blocks = [block.strip() for block in re.split(r"\n\s*\n", normalized) if block.strip()]
        candidates: list[ChunkCandidate] = []

        for block in blocks:
            section_title = self._try_heading(block)
            sentences = self._split_sentences(block)
            if not sentences:
                continue

            windows = self._window_sentences(sentences)
            for window_text in windows:
                candidates.append(ChunkCandidate(text=window_text, section_title=section_title))

        return candidates

    def _normalize(self, text: str) -> str:
        lines = [line.strip() for line in (text or "").splitlines()]
        lines = [line for line in lines if line]
        return "\n".join(lines)

    def _split_sentences(self, block: str) -> list[str]:
        # Preserve punctuation-based sentence boundaries while keeping it lightweight.
        parts = re.split(r"(?<=[.!?])\s+", block)
        return [part.strip() for part in parts if part.strip()]

    def _window_sentences(self, sentences: list[str]) -> list[str]:
        chunks: list[str] = []
        current: list[str] = []
        current_words = 0

        for sentence in sentences:
            sentence_words = self._word_count(sentence)
            if sentence_words == 0:
                continue

            if current_words + sentence_words <= self.target_words:
                current.append(sentence)
                current_words += sentence_words
                continue

            if current:
                chunks.append(" ".join(current).strip())
                current = self._overlap_tail(current)
                current_words = self._word_count(" ".join(current)) if current else 0

            if sentence_words > self.target_words:
                chunks.extend(self._split_long_sentence(sentence))
            else:
                current.append(sentence)
                current_words += sentence_words

        if current:
            chunks.append(" ".join(current).strip())

        return [chunk for chunk in chunks if chunk]

    def _split_long_sentence(self, sentence: str) -> list[str]:
        words = sentence.split()
        if len(words) <= self.target_words:
            return [sentence]

        out: list[str] = []
        start = 0
        step = max(1, self.target_words - self.overlap_words)
        while start < len(words):
            window = words[start : start + self.target_words]
            out.append(" ".join(window))
            start += step
        return out

    def _overlap_tail(self, sentences: list[str]) -> list[str]:
        if self.overlap_words <= 0:
            return []

        merged = " ".join(sentences)
        words = merged.split()
        if not words:
            return []

        tail = words[-self.overlap_words :]
        return [" ".join(tail)] if tail else []

    def _word_count(self, text: str) -> int:
        return len(re.findall(r"\w+", text))

    def _try_heading(self, block: str) -> str | None:
        first_line = block.split("\n", 1)[0].strip()
        if not first_line:
            return None

        # Heuristic: short title-like line with title casing or trailing colon.
        if len(first_line) <= 80 and (first_line.endswith(":") or first_line == first_line.title()):
            return first_line.rstrip(":")
        return None


text_chunking_service = TextChunkingService()
