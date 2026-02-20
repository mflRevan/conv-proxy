from __future__ import annotations

import time
from typing import Optional

import numpy as np

from src.stt.base import STTBackend, TranscriptionResult


class MoonshineBackend(STTBackend):
    def __init__(self, model: str = "moonshine/tiny") -> None:
        self.model = model
        self._backend = _load_backend(model)

    @property
    def name(self) -> str:
        suffix = self.model.split("/")[-1]
        return f"moonshine-{suffix}"

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> TranscriptionResult:
        start = time.time()
        text = self._backend.transcribe(audio.astype(np.float32), sample_rate=sample_rate)
        return TranscriptionResult(
            text=text.strip(),
            duration_s=len(audio) / float(sample_rate),
            processing_time_s=time.time() - start,
        )

    def transcribe_file(self, path: str) -> TranscriptionResult:
        import soundfile as sf

        audio, sr = sf.read(path)
        if audio.ndim > 1:
            audio = np.mean(audio, axis=1)
        return self.transcribe(audio, sample_rate=sr)


def _load_backend(model_name: str):
    backend = _load_moonshine_onnx(model_name)
    if backend:
        return backend
    backend = _load_moonshine_torch(model_name)
    if backend:
        return backend
    raise ImportError("Moonshine backend not installed. Try `pip install useful-moonshine-onnx` or `pip install moonshine`.")


def _load_moonshine_onnx(model_name: str):
    try:
        from moonshine_onnx import MoonshineOnnxModel, transcribe as onnx_transcribe
    except Exception:
        return None

    class _OnnxBackend:
        def __init__(self, model_name: str) -> None:
            self.model = MoonshineOnnxModel(model_name=model_name)

        def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
            decoded = onnx_transcribe(audio, model=self.model)
            if isinstance(decoded, list):
                return decoded[0]
            return str(decoded)

    return _OnnxBackend(model_name)


def _load_moonshine_torch(model_name: str):
    try:
        import moonshine
    except Exception:
        return None

    class _TorchBackend:
        def __init__(self, model_name: str) -> None:
            self.model = moonshine.load(model_name)

        def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
            return self.model.transcribe(audio, sample_rate=sample_rate)

    return _TorchBackend(model_name)
