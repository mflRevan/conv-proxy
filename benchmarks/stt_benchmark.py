from __future__ import annotations

import time
from pathlib import Path
from typing import List

import numpy as np
import soundfile as sf

from stt.engine import create_stt, list_available
from tts.kokoro_streaming import KokoroStreamingTTS

SENTENCE = "Hello, I am Jarvis. This is a quick speech to text benchmark."


def resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    if orig_sr == target_sr:
        return audio
    duration = len(audio) / float(orig_sr)
    target_len = int(duration * target_sr)
    x_old = np.linspace(0, duration, num=len(audio), endpoint=False)
    x_new = np.linspace(0, duration, num=target_len, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def wer(ref: str, hyp: str) -> float:
    r = ref.lower().split()
    h = hyp.lower().split()
    dp = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        dp[i][0] = i
    for j in range(len(h) + 1):
        dp[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost,
            )
    return dp[-1][-1] / max(1, len(r))


def main() -> None:
    tts = KokoroStreamingTTS()
    audio = tts.synthesize(SENTENCE)
    audio_16k = resample(audio, tts.sample_rate, 16000)
    tmp_path = Path("/tmp/stt_benchmark.wav")
    sf.write(tmp_path, audio_16k, 16000)

    rows: List[dict] = []
    for backend_name in list_available():
        if backend_name == "browser":
            continue
        backend = create_stt(backend_name)
        start = time.time()
        result = backend.transcribe_file(str(tmp_path))
        elapsed = time.time() - start
        duration = len(audio_16k) / 16000
        rows.append(
            {
                "backend": backend_name,
                "text": result.text,
                "time": elapsed,
                "wer": wer(SENTENCE, result.text),
                "rtf": elapsed / duration,
            }
        )

    print("STT benchmark")
    print("=" * 60)
    for row in rows:
        print(
            f"{row['backend']:<16} | time {row['time']:.2f}s | WER {row['wer']:.2f} | RTF {row['rtf']:.2f}\n"
            f"  -> {row['text']}\n"
        )


if __name__ == "__main__":
    main()
