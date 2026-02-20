from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class WakewordDetector:
    enabled: bool = True
    threshold: float = 0.55
    models: list[str] = field(default_factory=lambda: ["hey jarvis"])

    _model: Optional[object] = None
    _available: bool = False

    def __post_init__(self):
        self._init_model()

    def _init_model(self):
        try:
            from openwakeword import Model
            from openwakeword.utils import download_models
            try:
                self._model = Model(wakeword_models=self.models, inference_framework="onnx")
            except Exception:
                # common on fresh installs: model files absent
                try:
                    download_models()
                except Exception:
                    pass
                try:
                    self._model = Model(wakeword_models=self.models, inference_framework="onnx")
                except Exception:
                    self._model = Model(inference_framework="onnx")
            self._available = True
            log.info("Wakeword detector loaded (models=%s)", self.models)
        except Exception as e:
            self._model = None
            self._available = False
            log.warning("Wakeword unavailable, falling back to always-on VAD: %s", e)

    @property
    def available(self) -> bool:
        return self._available

    def set_config(self, enabled: Optional[bool] = None, threshold: Optional[float] = None, models: Optional[list[str]] = None):
        if enabled is not None:
            self.enabled = bool(enabled)
        if threshold is not None:
            self.threshold = float(threshold)
        if models is not None and models:
            self.models = [str(m) for m in models]

    def detect(self, pcm_f32: np.ndarray, sample_rate: int = 16000) -> bool:
        if not self.enabled:
            return True
        if not self._available or self._model is None:
            return False

        try:
            pcm16 = np.clip(pcm_f32, -1.0, 1.0)
            pcm16 = (pcm16 * 32767).astype(np.int16)
            pred = self._model.predict(pcm16)
            for key, score in pred.items():
                k = str(key).lower()
                if ("jarvis" in k or any(m.lower() in k for m in self.models)) and float(score) >= self.threshold:
                    return True
            return False
        except Exception:
            return False
