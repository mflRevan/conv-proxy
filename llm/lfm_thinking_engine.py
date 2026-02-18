"""LFM2.5-Thinking GGUF engine wrapper (llama-cpp-python)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Generator, List, Optional

from llama_cpp import Llama


@dataclass
class LFMThinkingEngine:
    """GGUF-based engine for LFM2.5-1.2B-Thinking via llama-cpp-python."""

    model_path: str = "models/lfm-thinking/LFM2.5-1.2B-Thinking-Q4_0.gguf"
    n_ctx: int = 4096
    n_threads: Optional[int] = None
    n_batch: int = 256
    chat_format: str = "chatml"

    def __post_init__(self) -> None:
        threads = self.n_threads or max(1, os.cpu_count() or 4)
        self.n_threads = threads
        self._llm = Llama(
            model_path=self.model_path,
            n_ctx=self.n_ctx,
            n_threads=threads,
            n_batch=self.n_batch,
            chat_format=self.chat_format,
            verbose=False,
        )

    def start_server(self, *_args, **_kwargs) -> None:
        # Direct Python API; no server needed.
        return None

    def stop_server(self) -> None:
        return None

    def chat(
        self,
        messages: List[dict],
        max_tokens: int = 512,
        stream: bool = False,
        temperature: float = 0.05,
        top_k: int = 50,
        repetition_penalty: float = 1.05,
    ) -> str | Generator[str, None, None]:
        params = {
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_k": top_k,
            "repeat_penalty": repetition_penalty,
            "stream": stream,
        }

        self._llm.reset()

        if stream:
            def _iter() -> Generator[str, None, None]:
                for chunk in self._llm.create_chat_completion(**params):
                    delta = chunk["choices"][0].get("delta")
                    if delta and delta.get("content"):
                        yield delta["content"]

            return _iter()

        response = self._llm.create_chat_completion(**params)
        return response["choices"][0]["message"]["content"]

    def chat_stream(self, messages: List[dict], max_tokens: int = 512) -> Generator[str, None, None]:
        return self.chat(messages=messages, max_tokens=max_tokens, stream=True)  # type: ignore[return-value]

    def __enter__(self) -> "LFMThinkingEngine":
        self.start_server()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop_server()
