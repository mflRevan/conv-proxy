from __future__ import annotations

import numpy as np

from stt.base import STTBackend, TranscriptionResult


class BrowserSTTBackend(STTBackend):
    """Marker backend for browser-side SpeechRecognition."""

    @property
    def name(self) -> str:
        return "browser"

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> TranscriptionResult:
        raise RuntimeError("Browser STT runs client-side via Web Speech API.")

    def transcribe_file(self, path: str) -> TranscriptionResult:
        raise RuntimeError("Browser STT runs client-side via Web Speech API.")
