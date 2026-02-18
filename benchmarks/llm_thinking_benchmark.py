"""Benchmark LFM2.5-Thinking GGUF performance (and compare with Audio)."""
from __future__ import annotations

import os
import resource
import time
from typing import Dict, Iterable, List

from llm.lfm_engine import LFMAudioEngine
from llm.lfm_thinking_engine import LFMThinkingEngine


def peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def count_tokens(text: str) -> int:
    return max(1, len(text.split())) if text else 0


def run_case(engine, messages: List[Dict], max_tokens: int = 256) -> Dict[str, float]:
    t_start = time.perf_counter()
    ttft = None
    text = ""
    for chunk in engine.chat_stream(messages, max_tokens=max_tokens):
        if ttft is None:
            ttft = time.perf_counter() - t_start
        text += chunk
    total = time.perf_counter() - t_start
    tokens = count_tokens(text)
    ttft = ttft or total
    decode_time = max(1e-6, total - ttft)
    tok_per_sec = tokens / decode_time
    return {
        "ttft": ttft,
        "total": total,
        "tok_per_sec": tok_per_sec,
        "tokens": tokens,
        "peak_rss": peak_rss_mb(),
    }


def print_table(rows: List[Dict]) -> None:
    header = f"{'engine':<8} {'model':<24} {'threads':>7} {'case':<12} {'ttft(s)':>8} {'tok/s':>8} {'total(s)':>9} {'peak_mb':>9}"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['engine']:<8} {row['model']:<24} {row['threads']:>7} {row['case']:<12} "
            f"{row['ttft']:.3f} {row['tok_per_sec']:.2f} {row['total']:.3f} {row['peak_rss']:.1f}"
        )


def build_cases() -> List[tuple[str, List[Dict]]]:
    tool_system = (
        "You can call tools. Available tool: get_weather(location) -> returns a short string. "
        "When you need a tool, respond with JSON: {\"tool\": \"get_weather\", \"location\": \"<city>\"}."
    )
    return [
        ("greeting", [{"role": "user", "content": "Hello, who are you?"}]),
        (
            "medium",
            [{"role": "user", "content": "Explain what a conversational proxy is in 2 sentences."}],
        ),
        (
            "tool_use",
            [
                {"role": "system", "content": tool_system},
                {"role": "user", "content": "What's the weather in Paris?"},
            ],
        ),
        (
            "multi_turn",
            [
                {"role": "user", "content": "Hello."},
                {"role": "assistant", "content": "Hi!"},
                {"role": "user", "content": "What is your role?"},
                {"role": "assistant", "content": "I help with tasks."},
                {"role": "user", "content": "Share one fun fact."},
            ],
        ),
    ]


def benchmark_thinking(models: List[str], thread_counts: Iterable[int]) -> List[Dict]:
    results: List[Dict] = []
    cases = build_cases()
    for model_path in models:
        model_name = os.path.basename(model_path)
        for threads in thread_counts:
            engine = LFMThinkingEngine(model_path=model_path, n_threads=threads)
            for case_name, messages in cases:
                metrics = run_case(engine, messages)
                results.append(
                    {
                        "engine": "thinking",
                        "model": model_name,
                        "threads": threads,
                        "case": case_name,
                        **metrics,
                    }
                )
    return results


def benchmark_audio() -> List[Dict]:
    results: List[Dict] = []
    cases = build_cases()
    engine = LFMAudioEngine()
    engine.start_server()
    try:
        for case_name, messages in cases:
            metrics = run_case(engine, messages)
            results.append(
                {
                    "engine": "audio",
                    "model": "LFM2.5-Audio-1.5B-Q4_0",
                    "threads": 0,
                    "case": case_name,
                    **metrics,
                }
            )
    finally:
        engine.stop_server()
    return results


def main() -> None:
    cpu_count = os.cpu_count() or 8
    thread_counts = [1, 2, 4, 8, cpu_count]
    thread_counts = sorted(set(t for t in thread_counts if t <= cpu_count))

    thinking_models = [
        path
        for path in [
            "models/lfm-thinking/LFM2.5-1.2B-Thinking-Q4_0.gguf",
            "models/lfm-thinking/LFM2.5-1.2B-Thinking-Q8_0.gguf",
        ]
        if os.path.exists(path)
    ]

    rows: List[Dict] = []
    if thinking_models:
        rows.extend(benchmark_thinking(thinking_models, thread_counts))
    else:
        print("No Thinking GGUFs found. Download models into models/lfm-thinking.")

    rows.extend(benchmark_audio())
    print_table(rows)


if __name__ == "__main__":
    main()
