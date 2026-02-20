from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.stt.base import STTBackend

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "runners" / "whisper-cli"
MODEL_DIR = ROOT / "models" / "whisper"

BACKENDS: Dict[str, Tuple[str, Dict[str, Any]]] = {
    "whisper-tiny": ("whisper_cpp", {"model": "tiny"}),
    "whisper-small": ("whisper_cpp", {"model": "small"}),
    "whisper-medium": ("whisper_cpp", {"model": "medium"}),
    "moonshine-tiny": ("moonshine", {"model": "moonshine/tiny"}),
    "moonshine-base": ("moonshine", {"model": "moonshine/base"}),
    "browser": ("browser", {}),
}

WHISPER_MODEL_MAP = {
    "whisper-tiny": "ggml-tiny.bin",
    "whisper-small": "ggml-small.bin",
    "whisper-medium": "ggml-medium.bin",
}


def create_stt(backend_name: str) -> STTBackend:
    if backend_name not in BACKENDS:
        raise ValueError(f"Unknown STT backend: {backend_name}")
    module_name, kwargs = BACKENDS[backend_name]
    module = import_module(f"src.stt.{module_name}")
    class_name = {
        "whisper_cpp": "WhisperCppBackend",
        "moonshine": "MoonshineBackend",
        "browser": "BrowserSTTBackend",
    }[module_name]
    backend_cls = getattr(module, class_name)
    return backend_cls(**kwargs)


def list_available() -> List[str]:
    available: List[str] = []
    for name in BACKENDS:
        if name.startswith("whisper"):
            if _whisper_ready(name):
                available.append(name)
        elif name.startswith("moonshine"):
            if _moonshine_ready():
                available.append(name)
        elif name == "browser":
            available.append(name)
    return available


def _whisper_ready(name: str) -> bool:
    model_file = WHISPER_MODEL_MAP.get(name)
    if not model_file:
        return False
    if not RUNNER.exists():
        return False
    if not RUNNER.is_file() or not RUNNER.stat().st_mode & 0o111:
        return False
    return (MODEL_DIR / model_file).exists()


def _moonshine_ready() -> bool:
    try:
        import_module("moonshine_onnx")
        return True
    except Exception:
        pass
    try:
        import_module("moonshine")
        return True
    except Exception:
        return False
