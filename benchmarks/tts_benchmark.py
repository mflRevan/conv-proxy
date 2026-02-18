"""Benchmark Kokoro streaming strategies."""
from __future__ import annotations

import time
from statistics import mean, median
from typing import Dict, List

import numpy as np

from tts.kokoro_streaming import KokoroStreamingTTS


TEXTS = {
    "short": "Hello. This is Jarvis.",
    "medium": (
        "Hello, I am Jarvis. This is a medium-length benchmark to test streaming "
        "performance and latency. We want to measure time to first audio and total runtime."
    ),
    "long": (
        "Hello, I am Jarvis. This is a longer benchmark passage intended to stress the streaming "
        "pipeline and produce many tokens of speech. We will split by sentences and words to observe "
        "how the streaming strategies behave under load. The goal is to keep latency low while "
        "maintaining smooth audio output and reasonable real-time factor."
    ),
}


def run_strategy(tts: KokoroStreamingTTS, text: str, strategy: str) -> Dict[str, float]:
    t_start = time.perf_counter()
    ttfa = None
    chunk_times: List[float] = []
    audio_len = 0

    last = t_start
    for audio in tts.synthesize_streaming(text, strategy=strategy):
        now = time.perf_counter()
        if ttfa is None:
            ttfa = now - t_start
        chunk_times.append(now - last)
        last = now
        audio_len += len(audio)

    total = time.perf_counter() - t_start
    audio_sec = audio_len / tts.sample_rate if tts.sample_rate else 0.0
    rtf = total / audio_sec if audio_sec > 0 else 0.0
    return {
        "ttfa": ttfa or 0.0,
        "total": total,
        "rtf": rtf,
        "chunk_mean": mean(chunk_times) if chunk_times else 0.0,
        "chunk_median": median(chunk_times) if chunk_times else 0.0,
        "chunks": len(chunk_times),
    }


def main() -> None:
    tts = KokoroStreamingTTS()
    strategies = ["sentence", "word_chunk", "native"]
    print("== Kokoro Streaming Benchmark ==")
    for label, text in TEXTS.items():
        print(f"\n-- Text: {label} --")
        for strat in strategies:
            metrics = run_strategy(tts, text, strat)
            print(
                f"{strat:>10} | TTFA {metrics['ttfa']:.3f}s | total {metrics['total']:.3f}s | "
                f"RTF {metrics['rtf']:.2f} | chunks {metrics['chunks']} | "
                f"chunk mean {metrics['chunk_mean']:.3f}s | median {metrics['chunk_median']:.3f}s"
            )


if __name__ == "__main__":
    main()
