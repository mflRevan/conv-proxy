"""Engine factory for LFM models."""
from __future__ import annotations

from typing import Any

from llm.lfm_engine import LFMAudioEngine
from llm.lfm_thinking_engine import LFMThinkingEngine


def create_engine(engine_type: str = "thinking", **kwargs: Any):
    if engine_type == "thinking":
        return LFMThinkingEngine(**kwargs)
    if engine_type == "audio":
        return LFMAudioEngine(**kwargs)
    raise ValueError(f"Unknown engine_type: {engine_type}")
