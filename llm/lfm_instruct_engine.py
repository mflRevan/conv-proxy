"""LFM2.5-Instruct GGUF engine wrapper (llama-cpp-python)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from threading import Lock
from typing import Generator, List, Optional

from llama_cpp import Llama

_TOOL_CALL_RE = re.compile(r"<\|tool_call_start\|>(.*?)<\|tool_call_end\|>", re.DOTALL)


@dataclass
class LFMInstructEngine:
    model_path: str = "models/lfm-instruct/LFM2.5-1.2B-Instruct-Q4_0.gguf"
    n_ctx: int = 4096
    n_threads: Optional[int] = None
    n_batch: int = 256
    n_gpu_layers: int = 0
    chat_format: str = "chatml"

    def __post_init__(self) -> None:
        threads = self.n_threads or max(1, os.cpu_count() or 4)
        self.n_threads = threads
        self._llm = Llama(
            model_path=self.model_path,
            n_ctx=self.n_ctx,
            n_threads=threads,
            n_batch=self.n_batch,
            n_gpu_layers=self.n_gpu_layers,
            chat_format=self.chat_format,
            verbose=False,
        )
        self._lock = Lock()

    def start_server(self, *_a, **_kw) -> None:
        return None

    def stop_server(self) -> None:
        return None

    def chat(self, messages: List[dict], max_tokens: int = 512,
             stream: bool = False, temperature: float = 0.3,
             top_k: int = 50, repetition_penalty: float = 1.05) -> str:
        with self._lock:
            self._llm.reset()
            response = self._llm.create_chat_completion(
                messages=messages, max_tokens=max_tokens,
                temperature=temperature, top_k=top_k,
                repeat_penalty=repetition_penalty, stream=False,
            )
            return response["choices"][0]["message"]["content"]

    def chat_stream(self, messages: List[dict], max_tokens: int = 512,
                    temperature: float = 0.3) -> Generator[str, None, None]:
        """Yield raw tokens (no thinking blocks in instruct model)."""
        with self._lock:
            self._llm.reset()
            for chunk in self._llm.create_chat_completion(
                messages=messages, max_tokens=max_tokens,
                temperature=temperature, top_k=50,
                repeat_penalty=1.05, stream=True,
            ):
                delta = chunk["choices"][0].get("delta")
                if delta and delta.get("content"):
                    yield delta["content"]

    @staticmethod
    def parse_tool_calls(text: str) -> list[dict]:
        """Extract tool calls from model output."""
        calls = []
        for m in _TOOL_CALL_RE.finditer(text):
            raw = m.group(1).strip()
            calls.append({"raw": raw})
        return calls

    @staticmethod
    def strip_tool_calls(text: str) -> str:
        """Remove tool call tokens from visible output."""
        return _TOOL_CALL_RE.sub("", text).strip()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass
