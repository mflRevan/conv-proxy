"""
Conv-proxy webapp: FastAPI backend with OpenRouter proxy controller.

Features:
- WebSocket for real-time streaming conversation
- STT transcription (Moonshine/Whisper)
- TTS output (Kokoro)
- LLM via OpenRouter (GPT-OSS-120B default)
- Tool calling: interrupt_agent, set_queued_task
- Stream cancellation on user interrupt
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

import numpy as np
import soundfile as sf
from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from llm.openrouter_engine import OpenRouterEngine
from proxy.controller import ProxyController, ProxyState
from stt.engine import create_stt, list_available
from tts.kokoro_streaming import KokoroStreamingTTS

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DIST_DIR = ROOT / "dist"

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")

# ─── Config ───
DEFAULT_STT_BACKEND = os.getenv("STT_BACKEND", "moonshine-tiny")
MODEL = os.getenv("PROXY_MODEL", "openai/gpt-oss-120b")
REASONING = os.getenv("PROXY_REASONING", "true").lower() == "true"
DISPATCH_DELAY = float(os.getenv("DISPATCH_DELAY", "10"))

# ─── Engines ───
_engine = OpenRouterEngine(model=MODEL, reasoning=REASONING)
_tts = KokoroStreamingTTS()
_pool = ThreadPoolExecutor(max_workers=4)

# ─── Global proxy controller ───
_proxy = ProxyController(
    engine=_engine,
    state=ProxyState(dispatch_delay=DISPATCH_DELAY),
)

# Track active stream cancellation per connection
_cancel_events: dict[int, threading.Event] = {}


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


# ─── Routes ───

@app.get("/")
def index() -> FileResponse:
    svelte_index = DIST_DIR / "index.html"
    if svelte_index.exists():
        return FileResponse(svelte_index)
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
def api_status() -> JSONResponse:
    return JSONResponse({
        "model": _engine.model,
        "reasoning": _engine.reasoning,
        "agent_status": _proxy.state.agent_status,
        "agent_task": _proxy.state.agent_current_task,
        "queued_task": _proxy.state.queued_task,
        "conversation_length": len(_proxy.conversation),
    })


@app.post("/api/agent-context")
async def update_agent_context(body: dict) -> JSONResponse:
    """Update live agent context (called by OpenClaw integration)."""
    _proxy.update_agent_context(
        status=body.get("status", "idle"),
        current_task=body.get("current_task", ""),
        turns=body.get("turns"),
        compressed_context=body.get("compressed_context", ""),
    )
    return JSONResponse({"ok": True})


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


class ChatRequest(BaseModel):
    message: str
    tts: bool = False


@app.post("/api/chat")
async def chat_http(request: ChatRequest) -> JSONResponse:
    """Non-streaming chat endpoint."""
    text = request.message.strip()
    if not text:
        return JSONResponse({"error": "Empty message"}, status_code=400)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(_pool, lambda: _proxy.process_message(text))

    payload = {
        "text": result["reply"],
        "action": result["action"],
        "task_draft": result["task_draft"],
        "tool_calls": result["tool_calls"],
        "timings": result["timings"],
    }

    if request.tts and result["reply"]:
        def _tts():
            t0 = time.monotonic()
            ttfa = None
            chunks = []
            for a in _tts.synthesize_streaming(result["reply"], strategy="sentence"):
                if ttfa is None:
                    ttfa = (time.monotonic() - t0) * 1000
                chunks.append(pcm16_base64(a))
            return chunks, ttfa or 0.0
        audio_chunks, ttfa_ms = await loop.run_in_executor(_pool, _tts)
        payload["audio"] = audio_chunks
        payload["sample_rate"] = _tts.sample_rate
        payload["ttfa_ms"] = ttfa_ms

    return JSONResponse(payload)


@app.websocket("/ws/chat")
async def chat_ws(ws: WebSocket) -> None:
    await ws.accept()
    conn_id = id(ws)
    cancel_event = threading.Event()
    _cancel_events[conn_id] = cancel_event

    await ws.send_text(json.dumps({
        "type": "status", "status": "connected",
        "model": _engine.model,
        "agent_status": _proxy.state.agent_status,
    }))

    loop = asyncio.get_event_loop()

    try:
        while True:
            raw = await ws.receive_text()
            payload = json.loads(raw)
            msg_type = payload.get("type", "message")

            # ─── Cancel active stream ───
            if msg_type == "cancel":
                cancel_event.set()
                # Create fresh event for next request
                cancel_event = threading.Event()
                _cancel_events[conn_id] = cancel_event
                await ws.send_text(json.dumps({"type": "cancelled"}))
                continue

            # ─── STT audio ───
            if msg_type == "audio":
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

            # ─── Chat message ───
            text = payload.get("message", "").strip()
            want_tts = bool(payload.get("tts", True))
            if not text:
                continue

            # Cancel any prior stream
            cancel_event.set()
            cancel_event = threading.Event()
            _cancel_events[conn_id] = cancel_event

            # Stream LLM response
            q: asyncio.Queue = asyncio.Queue()

            def _stream(txt=text, ce=cancel_event):
                try:
                    for delta in _proxy.process_message_stream(txt, cancel_event=ce):
                        if ce.is_set():
                            loop.call_soon_threadsafe(q.put_nowait, ("cancelled", None))
                            return
                        loop.call_soon_threadsafe(q.put_nowait, (delta["type"], delta))
                except Exception as e:
                    loop.call_soon_threadsafe(q.put_nowait, ("error", {"message": str(e)}))
                finally:
                    loop.call_soon_threadsafe(q.put_nowait, ("_end", None))

            loop.run_in_executor(_pool, _stream)

            response_text = ""
            tts_cancelled = False

            while True:
                evt_type, evt_data = await q.get()

                if evt_type == "_end":
                    break

                if evt_type == "cancelled":
                    await ws.send_text(json.dumps({"type": "cancelled"}))
                    tts_cancelled = True
                    break

                if evt_type == "error":
                    await ws.send_text(json.dumps({"type": "error", "content": evt_data.get("message", "")}))
                    break

                if evt_type == "content":
                    response_text += evt_data["text"]
                    await ws.send_text(json.dumps({"type": "text", "content": evt_data["text"]}))

                elif evt_type == "reasoning":
                    await ws.send_text(json.dumps({"type": "reasoning", "content": evt_data["text"]}))

                elif evt_type == "action":
                    await ws.send_text(json.dumps({
                        "type": "action",
                        "action": evt_data.get("action", ""),
                        "task": evt_data.get("task", ""),
                        "task_draft": _proxy.state.queued_task,
                    }))

                elif evt_type == "done":
                    pass  # handled below

            # ─── TTS ───
            if want_tts and response_text and not tts_cancelled and not cancel_event.is_set():
                def _do_tts(rt=response_text, ce=cancel_event):
                    t0 = time.monotonic()
                    ttfa = None
                    out = []
                    for a in _tts.synthesize_streaming(rt, strategy="sentence"):
                        if ce.is_set():
                            return out, ttfa or 0.0, True
                        if ttfa is None:
                            ttfa = (time.monotonic() - t0) * 1000
                        out.append(pcm16_base64(a))
                    return out, ttfa or 0.0, False

                chunks, ttfa_ms, was_cancelled = await loop.run_in_executor(_pool, _do_tts)
                for i, c in enumerate(chunks):
                    if cancel_event.is_set():
                        break
                    await ws.send_text(json.dumps({
                        "type": "audio", "content": c,
                        "sample_rate": _tts.sample_rate, "format": "pcm16",
                        "ttfa_ms": ttfa_ms if i == 0 else None,
                    }))

            # Send agent state with done
            await ws.send_text(json.dumps({
                "type": "done",
                "agent_status": _proxy.state.agent_status,
                "task_draft": _proxy.state.queued_task,
            }))

    except WebSocketDisconnect:
        pass
    finally:
        _cancel_events.pop(conn_id, None)


# ─── Dispatch timer (background task) ───
async def _dispatch_loop():
    """Periodically check if queued task should be dispatched."""
    while True:
        await asyncio.sleep(2)
        task = _proxy.check_dispatch()
        if task:
            # TODO: Send to OpenClaw main agent session
            print(f"[DISPATCH] Would send to agent: {task[:80]}")


@app.on_event("startup")
async def _startup():
    asyncio.create_task(_dispatch_loop())
