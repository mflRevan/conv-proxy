"""Benchmark LFM2.5-Audio GGUF performance."""
from __future__ import annotations

import os
import time
from typing import Dict, List

import psutil

from llm.lfm_engine import LFMAudioEngine


def memory_rss_mb() -> float:
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)


def count_tokens(text: str) -> int:
    return max(1, len(text.split())) if text else 0


def run_case(engine: LFMAudioEngine, messages: List[Dict], label: str) -> Dict[str, float]:
    t_start = time.perf_counter()
    ttft = None
    out_tokens = 0
    full_text = ""
    for chunk in engine.chat_stream(messages, max_tokens=128):
        if ttft is None:
            ttft = time.perf_counter() - t_start
        full_text += chunk
    out_tokens = count_tokens(full_text)
    total = time.perf_counter() - t_start
    tok_per_sec = out_tokens / total if total > 0 else 0.0
    return {
        "label": label,
        "ttft": ttft or 0.0,
        "total": total,
        "tok_per_sec": tok_per_sec,
        "mem_mb": memory_rss_mb(),
    }


def main() -> None:
    engine = LFMAudioEngine()
    engine.start_server()
    cases = [
        ([{"role": "user", "content": "Hello, who are you?"}], "simple chat"),
        (
            [
                {"role": "user", "content": "Summarize the key benefits of EVs in one sentence."}
            ],
            "single-turn",
        ),
        (
            [
                {"role": "user", "content": "Hello."},
                {"role": "assistant", "content": "Hi!"},
                {"role": "user", "content": "Tell me a short joke."},
            ],
            "multi-turn",
        ),
    ]

    print("== LFM GGUF Benchmark (Q4_0) ==")
    try:
        for messages, label in cases:
            metrics = run_case(engine, messages, label)
            print(
                f"{metrics['label']:>12} | TTFT {metrics['ttft']:.3f}s | total {metrics['total']:.3f}s | "
                f"tok/s {metrics['tok_per_sec']:.2f} | mem {metrics['mem_mb']:.1f} MB"
            )
    finally:
        engine.stop_server()


if __name__ == "__main__":
    main()
