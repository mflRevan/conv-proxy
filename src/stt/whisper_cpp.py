from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from src.stt.base import STTBackend, TranscriptionResult

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "runners" / "whisper-cli"
MODEL_DIR = ROOT / "models" / "whisper"

MODEL_MAP = {
    "tiny": "ggml-tiny.bin",
    "small": "ggml-small.bin",
    "medium": "ggml-medium.bin",
}


class WhisperCppBackend(STTBackend):
    def __init__(self, model: str = "tiny") -> None:
        if model not in MODEL_MAP:
            raise ValueError(f"Unknown whisper.cpp model: {model}")
        self.model = model

    @property
    def name(self) -> str:
        return f"whisper-{self.model}"

    def _model_path(self) -> Path:
        return MODEL_DIR / MODEL_MAP[self.model]

    def _ensure_ready(self) -> None:
        if not RUNNER.exists():
            raise FileNotFoundError(f"whisper-cli not found at {RUNNER}")
        if not RUNNER.is_file() or not RUNNER.stat().st_mode & 0o111:
            raise PermissionError(f"whisper-cli is not executable: {RUNNER}")
        if not self._model_path().exists():
            raise FileNotFoundError(
                f"Whisper model not found: {self._model_path()} (download into models/whisper)"
            )

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> TranscriptionResult:
        self._ensure_ready()
        start = time.time()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
            sf.write(tmp.name, audio, samplerate=sample_rate)
            result = self.transcribe_file(tmp.name)
        result.processing_time_s = time.time() - start
        result.duration_s = len(audio) / float(sample_rate)
        return result

    def transcribe_file(self, path: str) -> TranscriptionResult:
        self._ensure_ready()
        start = time.time()
        cmd = [
            str(RUNNER),
            "-m",
            str(self._model_path()),
            "-f",
            str(path),
            "--no-timestamps",
            "-nt",
        ]
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode("utf-8", errors="ignore")
        text = _extract_text(output)
        return TranscriptionResult(
            text=text.strip(),
            duration_s=0.0,
            processing_time_s=time.time() - start,
        )


def _extract_text(raw: str) -> str:
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    cleaned = []
    for line in lines:
        lower = line.lower()
        if lower.startswith("whisper") or lower.startswith("main"):
            continue
        if "system_info" in lower or "whisper" in lower and "cpu" in lower:
            continue
        if line.startswith("[") and "]" in line:
            # strip timestamps
            line = line.split("]", 1)[-1].strip()
        cleaned.append(line)
    if cleaned:
        return " ".join(cleaned)
    return raw.strip()
