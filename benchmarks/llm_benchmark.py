"""Benchmark LFM2.5-1.2B-Thinking performance."""
from __future__ import annotations

import os
import time
from typing import Dict, List

import psutil

from llm.lfm_engine import LFMEngine


def memory_rss_mb() -> float:
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)


def run_case(engine: LFMEngine, messages: List[Dict], label: str) -> Dict[str, float]:
    t_start = time.perf_counter()
    streamer = engine.generate(messages, stream=True, max_tokens=128)
    ttft = None
    out_tokens = 0
    for token in streamer:
        if ttft is None:
            ttft = time.perf_counter() - t_start
        out_tokens += 1
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
    engine = LFMEngine()
    cases = [
        ([{"role": "user", "content": "Hello, who are you?"}], "simple chat"),
        (
            [
                {"role": "user", "content": "Use a tool to lookup weather for Berlin."}
            ],
            "tool-use",
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

    print("== LFM Benchmark ==")
    for messages, label in cases:
        metrics = run_case(engine, messages, label)
        print(
            f"{metrics['label']:>10} | TTFT {metrics['ttft']:.3f}s | total {metrics['total']:.3f}s | "
            f"tok/s {metrics['tok_per_sec']:.2f} | mem {metrics['mem_mb']:.1f} MB"
        )


if __name__ == "__main__":
    main()
