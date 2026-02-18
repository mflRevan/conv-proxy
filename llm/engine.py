"""Engine factory for LFM models."""
from __future__ import annotations

import os
from typing import Any

from llm.lfm_engine import LFMAudioEngine
from llm.lfm_thinking_engine import LFMThinkingEngine
from llm.lfm_instruct_engine import LFMInstructEngine


def create_engine(engine_type: str = "instruct", **kwargs: Any):
    # Auto-detect GPU layers
    n_gpu = int(os.getenv("N_GPU_LAYERS", "0"))
    if n_gpu:
        kwargs.setdefault("n_gpu_layers", n_gpu)

    if engine_type == "instruct":
        return LFMInstructEngine(**kwargs)
    if engine_type == "thinking":
        return LFMThinkingEngine(**kwargs)
    if engine_type == "audio":
        return LFMAudioEngine(**kwargs)
    raise ValueError(f"Unknown engine_type: {engine_type}")
