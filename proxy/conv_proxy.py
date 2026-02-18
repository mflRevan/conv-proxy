"""Conversational proxy layer combining LFM and Kokoro."""
from __future__ import annotations

import time
from typing import Any, Dict, Generator, List, Optional

import numpy as np

from llm.engine import create_engine
from tts.kokoro_streaming import KokoroStreamingTTS


class ConversationalProxy:
    """Lightweight proxy that handles conversation and streaming audio."""

    def __init__(
        self,
        max_tokens: int = 2048,
        engine_type: str = "audio",
        engine: Optional[Any] = None,
        tts: Optional[KokoroStreamingTTS] = None,
    ) -> None:
        self.max_tokens = max_tokens
        self.history: List[Dict] = []
        self.last_interaction: Optional[float] = None
        self.engine = engine or create_engine(engine_type=engine_type)
        self.tts = tts or KokoroStreamingTTS()
        self.system_prompt = self._load_system_prompt()
        if self.system_prompt:
            self.history.append({"role": "system", "content": self.system_prompt})
        self.engine.start_server()

    def _load_system_prompt(self) -> str:
        try:
            with open("config/PROXY.md", "r", encoding="utf-8") as f:
                return f.read().strip()
        except FileNotFoundError:
            return ""

    def _trim_history(self) -> None:
        # rough token estimate: 4 chars per token
        while True:
            chars = sum(len(m.get("content", "")) for m in self.history)
            approx_tokens = chars // 4
            if approx_tokens <= self.max_tokens or len(self.history) <= 1:
                break
            self.history.pop(1)

    def process_input(self, text: str) -> Generator[np.ndarray, None, None]:
        self.history.append({"role": "user", "content": text})
        self._trim_history()
        response = self.engine.chat(self.history, stream=False, max_tokens=256)
        self.history.append({"role": "assistant", "content": response})
        self._trim_history()
        self.last_interaction = time.time()
        for audio in self.tts.synthesize_streaming(response, strategy="sentence"):
            yield audio

    def relay_to_agent(self, task: str) -> str:
        return f"[Relay Task] {task}"

    def inject_context(self, context: str) -> None:
        self.history.append({"role": "system", "content": context})
        self._trim_history()

    def interrupt(self) -> str:
        return "<INTERRUPT>"

    def get_status(self) -> Dict:
        return {
            "history_length": len(self.history),
            "last_interaction": self.last_interaction,
            "max_tokens": self.max_tokens,
        }
