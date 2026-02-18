from __future__ import annotations

import numpy as np

from llm.lfm_engine import LFMEngine
from proxy.conv_proxy import ConversationalProxy
from tts.kokoro_streaming import KokoroStreamingTTS


def test_tts_strategies():
    tts = KokoroStreamingTTS()
    text = "Hello. This is a test of streaming."
    full = tts.synthesize(text)
    assert isinstance(full, np.ndarray)
    assert full.size > 0
    for strategy in ["sentence", "word_chunk", "native"]:
        chunks = list(tts.synthesize_streaming(text, strategy=strategy))
        assert len(chunks) > 0
        assert all(isinstance(c, np.ndarray) for c in chunks)


def test_lfm_engine_basic():
    engine = LFMEngine()
    out = engine.generate([{"role": "user", "content": "Say hello."}], max_tokens=16, stream=False)
    assert isinstance(out, str)
    fake = "<|tool_call_start|>[search(query=\"hi\")]<|tool_call_end|>"
    calls = engine.parse_tool_calls(fake)
    assert calls and calls[0]["name"] == "search"


def test_proxy_end_to_end():
    engine = LFMEngine()
    tts = KokoroStreamingTTS()
    proxy = ConversationalProxy(engine=engine, tts=tts)
    chunks = list(proxy.process_input("Hello there."))
    assert len(chunks) > 0
