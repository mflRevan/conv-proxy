"""Streaming wrapper for Kokoro TTS."""
from __future__ import annotations

import re
import threading
from typing import Generator, Iterable, List

import numpy as np
from kokoro import KPipeline


_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


class KokoroStreamingTTS:
    """Thread-safe streaming wrapper for Kokoro KPipeline."""

    def __init__(self, lang_code: str = "a", voice: str = "af_heart", sample_rate: int = 24000) -> None:
        self.lang_code = lang_code
        self.voice = voice
        self.sample_rate = sample_rate
        self.pipeline = KPipeline(lang_code=lang_code)
        self._lock = threading.Lock()
        self.word_chunk_size = 20
        self.warmup()

    def warmup(self) -> None:
        """Prime the pipeline with a short utterance."""
        with self._lock:
            for _, _, _audio in self.pipeline("warm up", voice=self.voice):
                break

    def synthesize(self, text: str) -> np.ndarray:
        """Synthesize full audio for the given text."""
        chunks: List[np.ndarray] = []
        with self._lock:
            for _, _, audio in self.pipeline(text, voice=self.voice):
                chunks.append(np.asarray(audio))
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks)

    def _iter_pipeline(self, text: str) -> Iterable[np.ndarray]:
        with self._lock:
            for _, _, audio in self.pipeline(text, voice=self.voice):
                yield np.asarray(audio)

    def _split_sentences(self, text: str) -> List[str]:
        parts = [p.strip() for p in _SENTENCE_RE.split(text) if p.strip()]
        return parts if parts else [text]

    def _split_word_chunks(self, text: str) -> List[str]:
        words = text.split()
        if not words:
            return [text]
        chunks: List[str] = []
        for i in range(0, len(words), self.word_chunk_size):
            chunks.append(" ".join(words[i : i + self.word_chunk_size]))
        return chunks

    def synthesize_streaming(self, text: str, strategy: str = "sentence") -> Generator[np.ndarray, None, None]:
        """Yield streaming audio chunks according to strategy."""
        strategy = strategy.lower()
        if strategy == "native":
            for audio in self._iter_pipeline(text):
                yield audio
            return
        if strategy == "sentence":
            chunks = self._split_sentences(text)
        elif strategy == "word_chunk":
            chunks = self._split_word_chunks(text)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

        for chunk in chunks:
            for audio in self._iter_pipeline(chunk):
                yield audio
