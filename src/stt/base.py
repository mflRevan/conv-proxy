from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class TranscriptionResult:
    text: str
    language: Optional[str] = None
    duration_s: float = 0.0
    processing_time_s: float = 0.0


class STTBackend(ABC):
    @abstractmethod
    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> TranscriptionResult:
        ...

    @abstractmethod
    def transcribe_file(self, path: str) -> TranscriptionResult:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...
