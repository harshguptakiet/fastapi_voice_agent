from __future__ import annotations

import re

_SENTENCE_RE = re.compile(r"[^.!?]+[.!?]")


class SentenceBufferService:
    """Splits assistant text into complete, TTS-friendly sentence chunks."""

    def split_for_tts(self, text: str, *, max_chunk_words: int = 18) -> list[str]:
        content = (text or "").strip()
        if not content:
            return []

        base_sentences = [m.group(0).strip() for m in _SENTENCE_RE.finditer(content)]
        if not base_sentences:
            base_sentences = [content if content[-1] in ".!?" else f"{content}."]

        chunks: list[str] = []
        for sentence in base_sentences:
            words = sentence.split()
            if len(words) <= max_chunk_words:
                chunks.append(sentence)
                continue

            # Split long sentences into short speakable chunks.
            current: list[str] = []
            for word in words:
                current.append(word)
                if len(current) >= max_chunk_words:
                    chunk = " ".join(current).rstrip(" ,;:-")
                    if chunk and chunk[-1] not in ".!?":
                        chunk += "."
                    chunks.append(chunk)
                    current = []
            if current:
                chunk = " ".join(current).rstrip(" ,;:-")
                if chunk and chunk[-1] not in ".!?":
                    chunk += "."
                chunks.append(chunk)

        return chunks

    def pop_leading_speech_chunks(
        self, buffer: str, *, max_chunk_words: int = 18
    ) -> tuple[list[str], str]:
        """Extract TTS-ready chunks from complete leading sentences; keep remainder."""
        chunks_out: list[str] = []
        rest = buffer or ""
        while True:
            m = _SENTENCE_RE.match(rest)
            if not m:
                break
            sentence = m.group(0).strip()
            rest = rest[m.end() :].lstrip()
            chunks_out.extend(self.split_for_tts(sentence, max_chunk_words=max_chunk_words))
        return chunks_out, rest


sentence_buffer_service = SentenceBufferService()
