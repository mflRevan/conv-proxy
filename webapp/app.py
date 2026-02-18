from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional
import time

import numpy as np
import soundfile as sf
from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from llm.engine import create_engine
from stt.engine import create_stt, list_available
from tts.kokoro_streaming import KokoroStreamingTTS

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DIST_DIR = ROOT / "dist"  # Svelte build output

app = FastAPI()
# Serve old static files as fallback
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
# Serve Svelte dist assets
if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")

_THINK_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)
_TOOL_CALL_RE = re.compile(r"<\|tool_call_start\|>(.*?)<\|tool_call_end\|>", re.DOTALL)


def resolve_engine_type() -> str:
    return os.getenv("ENGINE_TYPE", "instruct")


def resolve_stt_backend() -> str:
    return os.getenv("STT_BACKEND", "moonshine-tiny")


engine_type = resolve_engine_type()
engine = create_engine(engine_type=engine_type)
tts_engine = KokoroStreamingTTS()
DEFAULT_STT_BACKEND = resolve_stt_backend()
_pool = ThreadPoolExecutor(max_workers=2)


def load_system_prompt() -> str:
    try:
        return Path("config/PROXY.md").read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def pcm16_base64(audio: np.ndarray) -> str:
    if audio.size == 0:
        return ""
    audio_clipped = np.clip(audio, -1.0, 1.0)
    pcm16 = (audio_clipped * 32767).astype(np.int16)
    return base64.b64encode(pcm16.tobytes()).decode("utf-8")


def decode_wav_bytes(payload: bytes) -> tuple[np.ndarray, int]:
    audio, sr = sf.read(io.BytesIO(payload), dtype="float32")
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    return audio, sr


def split_thinking(raw: str) -> tuple[str, str]:
    """Split raw LLM output into (thinking, answer)."""
    m = _THINK_RE.search(raw)
    if m:
        thinking = m.group(1).strip()
        answer = _THINK_RE.sub("", raw).strip()
    else:
        thinking = ""
        answer = raw.strip()
    # Strip tool calls from visible answer
    answer = _TOOL_CALL_RE.sub("", answer).strip()
    return thinking, answer


def parse_tool_calls(raw: str) -> list[dict]:
    """Extract tool calls from raw output."""
    calls = []
    for m in _TOOL_CALL_RE.finditer(raw):
        calls.append({"raw": m.group(1).strip()})
    return calls


class ChatRequest(BaseModel):
    message: str
    tts: bool = False


@app.on_event("startup")
def _startup() -> None:
    engine.start_server()


@app.get("/")
def index() -> FileResponse:
    # Prefer Svelte build if available
    svelte_index = DIST_DIR / "index.html"
    if svelte_index.exists():
        return FileResponse(svelte_index)
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/stt/backends")
def stt_backends() -> JSONResponse:
    return JSONResponse({"backends": list_available(), "default": DEFAULT_STT_BACKEND})


@app.post("/api/stt/transcribe")
async def stt_transcribe(file: UploadFile = File(...), stt_backend: Optional[str] = None) -> JSONResponse:
    backend_name = stt_backend or DEFAULT_STT_BACKEND
    stt = create_stt(backend_name)
    data = await file.read()
    audio, sr = decode_wav_bytes(data)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(_pool, lambda: stt.transcribe(audio, sample_rate=sr))
    return JSONResponse({"text": result.text, "backend": backend_name})


@app.post("/api/chat")
async def chat_http(request: ChatRequest) -> JSONResponse:
    text = request.message.strip()
    if not text:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    history: List[dict] = []
    sp = load_system_prompt()
    if sp:
        history.append({"role": "system", "content": sp})
    history.append({"role": "user", "content": text})

    loop = asyncio.get_event_loop()
    raw = await loop.run_in_executor(_pool, lambda: engine.chat(history, max_tokens=512))
    thinking, answer = split_thinking(raw)
    tool_calls = parse_tool_calls(raw)

    payload: dict = {"text": answer, "thinking": thinking}
    if tool_calls:
        payload["tool_calls"] = tool_calls

    if request.tts and answer:
        def _tts():
            t0 = time.monotonic()
            ttfa = None
            chunks = []
            for a in tts_engine.synthesize_streaming(answer, strategy="sentence"):
                if ttfa is None:
                    ttfa = (time.monotonic() - t0) * 1000
                chunks.append(pcm16_base64(a))
            return chunks, ttfa or 0.0
        audio_chunks, ttfa_ms = await loop.run_in_executor(_pool, _tts)
        payload["audio"] = audio_chunks
        payload["sample_rate"] = tts_engine.sample_rate
        payload["ttfa_ms"] = ttfa_ms

    return JSONResponse(payload)


@app.websocket("/ws/chat")
async def chat_ws(ws: WebSocket) -> None:
    await ws.accept()
    history: List[dict] = []
    sp = load_system_prompt()
    if sp:
        history.append({"role": "system", "content": sp})

    await ws.send_text(json.dumps({"type": "status", "status": "connected"}))
    loop = asyncio.get_event_loop()

    try:
        while True:
            raw = await ws.receive_text()
            payload = json.loads(raw)
            payload_type = payload.get("type", "message")

            # STT audio
            if payload_type == "audio":
                backend_name = payload.get("stt_backend") or DEFAULT_STT_BACKEND
                audio_b64 = payload.get("data", "")
                if not audio_b64:
                    continue
                audio_bytes = base64.b64decode(audio_b64)
                def _stt(ab=audio_bytes, bn=backend_name):
                    a, sr = decode_wav_bytes(ab)
                    return create_stt(bn).transcribe(a, sample_rate=sr)
                result = await loop.run_in_executor(_pool, _stt)
                await ws.send_text(json.dumps({"type": "stt", "text": result.text}))
                continue

            text = payload.get("message", "").strip()
            want_tts = bool(payload.get("tts", False))
            if not text:
                continue
            history.append({"role": "user", "content": text})

            # Stream LLM in thread, parse think blocks
            q: asyncio.Queue = asyncio.Queue()

            def _llm():
                try:
                    full_buf = ""
                    in_think = False
                    in_tool = False
                    think_buf = ""
                    tool_buf = ""
                    text_buf = ""
                    for tok in engine.chat_stream(history, max_tokens=512):
                        full_buf += tok

                        # --- Think block detection ---
                        if "<think>" in full_buf and not in_think and not in_tool:
                            in_think = True
                            before = full_buf.split("<think>")[0]
                            if before.strip():
                                loop.call_soon_threadsafe(q.put_nowait, ("text", before))
                            think_buf = full_buf.split("<think>", 1)[1]
                            full_buf = ""
                            continue

                        if in_think:
                            think_buf += tok
                            if "</think>" in think_buf:
                                in_think = False
                                thinking = think_buf.split("</think>")[0].strip()
                                after = think_buf.split("</think>", 1)[1]
                                loop.call_soon_threadsafe(q.put_nowait, ("thinking", thinking))
                                full_buf = after
                                think_buf = ""
                            continue

                        # --- Tool call detection ---
                        if "<|tool_call_start|>" in full_buf and not in_tool:
                            in_tool = True
                            before = full_buf.split("<|tool_call_start|>")[0]
                            if before.strip():
                                loop.call_soon_threadsafe(q.put_nowait, ("text", before))
                            tool_buf = full_buf.split("<|tool_call_start|>", 1)[1]
                            full_buf = ""
                            continue

                        if in_tool:
                            tool_buf += tok
                            if "<|tool_call_end|>" in tool_buf:
                                in_tool = False
                                raw_call = tool_buf.split("<|tool_call_end|>")[0].strip()
                                after = tool_buf.split("<|tool_call_end|>", 1)[1]
                                loop.call_soon_threadsafe(q.put_nowait, ("tool_call", raw_call))
                                full_buf = after
                                tool_buf = ""
                            continue

                        # Normal text - emit token by token
                        loop.call_soon_threadsafe(q.put_nowait, ("text", tok))
                        full_buf = ""
                except Exception as e:
                    loop.call_soon_threadsafe(q.put_nowait, ("error", str(e)))
                finally:
                    loop.call_soon_threadsafe(q.put_nowait, ("end", None))

            loop.run_in_executor(_pool, _llm)

            response_text = ""
            thinking_text = ""
            tool_calls = []
            while True:
                msg_type, msg_data = await q.get()
                if msg_type == "end":
                    break
                if msg_type == "error":
                    await ws.send_text(json.dumps({"type": "error", "content": msg_data}))
                    break
                if msg_type == "thinking":
                    thinking_text = msg_data
                    await ws.send_text(json.dumps({"type": "thinking", "content": msg_data}))
                elif msg_type == "tool_call":
                    tool_calls.append({"raw": msg_data})
                    await ws.send_text(json.dumps({"type": "tool_call", "content": {"raw": msg_data}}))
                elif msg_type == "text":
                    response_text += msg_data
                    await ws.send_text(json.dumps({"type": "text", "content": msg_data}))

            history.append({"role": "assistant", "content": response_text})

            if want_tts and response_text:
                def _tts(rt=response_text):
                    t0 = time.monotonic()
                    ttfa = None
                    out = []
                    for a in tts_engine.synthesize_streaming(rt, strategy="sentence"):
                        if ttfa is None:
                            ttfa = (time.monotonic() - t0) * 1000
                        out.append(pcm16_base64(a))
                    return out, (ttfa or 0.0)
                chunks, ttfa_ms = await loop.run_in_executor(_pool, _tts)
                for i, c in enumerate(chunks):
                    await ws.send_text(json.dumps({
                        "type": "audio", "content": c,
                        "sample_rate": tts_engine.sample_rate, "format": "pcm16",
                        "ttfa_ms": ttfa_ms if i == 0 else None
                    }))

            await ws.send_text(json.dumps({"type": "done"}))
    except WebSocketDisconnect:
        return
