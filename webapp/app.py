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
_chat_clients: set[WebSocket] = set()
_voice_clients: set[WebSocket] = set()


async def _broadcast(msg: dict):
    payload = json.dumps(msg)
    stale: list[WebSocket] = []
    for ws in list(_chat_clients | _voice_clients):
        try:
            await ws.send_text(payload)
        except Exception:
            stale.append(ws)
    for ws in stale:
        _chat_clients.discard(ws)
        _voice_clients.discard(ws)


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
        "scratchpad_task": _proxy.state.scratchpad_task,
        "queued_task": _proxy.state.queued_task,
        "must_brief_before_dispatch": _proxy.state.must_brief_before_dispatch,
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
        just_finished=bool(body.get("just_finished", False)),
        completion_brief=body.get("completion_brief", ""),
    )

    brief = _proxy.pop_pending_completion_brief()
    if brief:
        await _broadcast({"type": "agent_brief", "content": brief})

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
        "queued_task": result.get("queued_task", ""),
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
    _chat_clients.add(ws)
    conn_id = id(ws)
    cancel_event = threading.Event()
    _cancel_events[conn_id] = cancel_event

    await ws.send_text(json.dumps({
        "type": "status", "status": "connected",
        "model": _engine.model,
        "agent_status": _proxy.state.agent_status,
        "task_draft": _proxy.state.scratchpad_task,
        "queued_task": _proxy.state.queued_task,
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
                        "task_draft": _proxy.state.scratchpad_task,
                        "queued_task": _proxy.state.queued_task,
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
                "task_draft": _proxy.state.scratchpad_task,
                "queued_task": _proxy.state.queued_task,
            }))

    except WebSocketDisconnect:
        pass
    finally:
        _cancel_events.pop(conn_id, None)
        _chat_clients.discard(ws)


# ─── Real-time Voice WebSocket ───

from voice.pipeline import VoicePipeline, PipelineState, VADConfig

@app.websocket("/ws/voice")
async def voice_ws(ws: WebSocket) -> None:
    """
    Real-time voice conversation WebSocket.
    
    Client sends:
      - {"type": "audio_chunk", "data": "<base64_pcm16>", "sample_rate": 16000}
      - {"type": "cancel"}  — interrupt current response
      - {"type": "config", "vad": {...}, "stt_backend": "...", "tts": true/false}
      - {"type": "text", "message": "..."} — text fallback input
    
    Server sends:
      - {"type": "state", "state": "idle|listening|processing|speaking"}
      - {"type": "vad", "event": "speech_start|speech_end|barge_in"}
      - {"type": "transcription", "text": "...", "final": true/false}
      - {"type": "text", "content": "..."} — streaming LLM tokens
      - {"type": "action", "action": "task|stop", ...}
      - {"type": "reasoning", "content": "..."}
      - {"type": "audio", "content": "<base64_pcm16>", "sample_rate": 24000}
      - {"type": "done", "task_draft": "...", "agent_status": "..."}
      - {"type": "cancelled"}
      - {"type": "error", "message": "..."}
    """
    await ws.accept()
    _voice_clients.add(ws)

    pipeline = VoicePipeline(stt_backend=DEFAULT_STT_BACKEND, tts_engine=_tts)
    want_tts = True
    loop = asyncio.get_event_loop()
    
    async def send(msg: dict):
        try:
            await ws.send_text(json.dumps(msg))
        except Exception:
            pass

    # Wire pipeline callbacks
    def on_state(s: PipelineState):
        asyncio.run_coroutine_threadsafe(send({"type": "state", "state": s.name.lower()}), loop)
    
    def on_vad(event: str):
        asyncio.run_coroutine_threadsafe(send({"type": "vad", "event": event}), loop)
    
    pipeline.on_state_change = on_state
    pipeline.on_vad_event = on_vad

    await send({
        "type": "status", "status": "connected",
        "model": _engine.model,
        "agent_status": _proxy.state.agent_status,
        "task_draft": _proxy.state.scratchpad_task,
        "queued_task": _proxy.state.queued_task,
        "stt_backend": pipeline.stt_backend,
        "vad_config": {
            "energy_threshold": pipeline.vad_config.energy_threshold,
            "silence_duration_ms": pipeline.vad_config.silence_duration_ms,
            "min_speech_ms": pipeline.vad_config.min_speech_ms,
        },
    })

    async def run_response(text: str):
        """Full LLM → TTS response pipeline with cancellation."""
        cancel_event = pipeline.start_response()
        pipeline._set_state(PipelineState.PROCESSING)
        
        # Stream LLM
        q: asyncio.Queue = asyncio.Queue()
        
        def _stream():
            try:
                for delta in _proxy.process_message_stream(text, cancel_event=cancel_event):
                    if cancel_event.is_set():
                        loop.call_soon_threadsafe(q.put_nowait, ("cancelled", None))
                        return
                    loop.call_soon_threadsafe(q.put_nowait, (delta["type"], delta))
            except Exception as e:
                loop.call_soon_threadsafe(q.put_nowait, ("error", {"message": str(e)}))
            finally:
                loop.call_soon_threadsafe(q.put_nowait, ("_end", None))
        
        loop.run_in_executor(_pool, _stream)
        
        response_text = ""
        was_cancelled = False
        
        while True:
            evt_type, evt_data = await q.get()
            
            if evt_type == "_end":
                break
            if evt_type == "cancelled":
                await send({"type": "cancelled"})
                was_cancelled = True
                break
            if evt_type == "error":
                await send({"type": "error", "message": evt_data.get("message", "")})
                break
            if evt_type == "content":
                response_text += evt_data["text"]
                await send({"type": "text", "content": evt_data["text"]})
            elif evt_type == "reasoning":
                await send({"type": "reasoning", "content": evt_data["text"]})
            elif evt_type == "action":
                await send({
                    "type": "action",
                    "action": evt_data.get("action", ""),
                    "task": evt_data.get("task", ""),
                    "task_draft": _proxy.state.scratchpad_task,
                    "queued_task": _proxy.state.queued_task,
                })
            elif evt_type == "done":
                pass
        
        # TTS
        if want_tts and response_text and not was_cancelled and not cancel_event.is_set():
            pipeline.begin_speaking()
            
            def _do_tts():
                chunks = []
                for b64, sr, is_first in pipeline.synthesize_streaming(response_text):
                    if cancel_event.is_set():
                        return chunks, True
                    chunks.append((b64, sr, is_first))
                return chunks, False
            
            tts_chunks, tts_cancelled = await loop.run_in_executor(_pool, _do_tts)
            
            for b64, sr, is_first in tts_chunks:
                if cancel_event.is_set():
                    break
                await send({
                    "type": "audio", "content": b64,
                    "sample_rate": sr, "format": "pcm16",
                    "first": is_first,
                })
        
        # Done
        if not was_cancelled:
            await send({
                "type": "done",
                "agent_status": _proxy.state.agent_status,
                "task_draft": _proxy.state.scratchpad_task,
                "queued_task": _proxy.state.queued_task,
            })
        
        pipeline.finish_response()

    try:
        while True:
            raw = await ws.receive_text()
            payload = json.loads(raw)
            msg_type = payload.get("type", "")

            # ─── Audio chunk (real-time VAD) ───
            if msg_type == "audio_chunk":
                b64 = payload.get("data", "")
                if not b64:
                    continue
                pcm_bytes = base64.b64decode(b64)
                pcm16 = np.frombuffer(pcm_bytes, dtype=np.int16)
                audio_f32 = pcm16.astype(np.float32) / 32768.0
                
                vad_result = pipeline.process_audio_chunk(audio_f32)
                
                if vad_result == "speech_end":
                    # Transcribe and process
                    text = await loop.run_in_executor(
                        _pool, pipeline.transcribe_buffer
                    )
                    if text:
                        await send({"type": "transcription", "text": text, "final": True})
                        await run_response(text)
                    else:
                        pipeline.finish_response()
                
                elif vad_result == "barge_in":
                    await send({"type": "cancelled"})
                    # Pipeline already cancelled output and switched to LISTENING

            # ─── Cancel ───
            elif msg_type == "cancel":
                pipeline.cancel_output()
                await send({"type": "cancelled"})

            # ─── Text fallback ───
            elif msg_type == "text":
                text = payload.get("message", "").strip()
                if text:
                    await run_response(text)

            # ─── Config update ───
            elif msg_type == "config":
                if "stt_backend" in payload:
                    pipeline.stt_backend = payload["stt_backend"]
                if "tts" in payload:
                    want_tts = bool(payload["tts"])
                if "vad" in payload:
                    vad = payload["vad"]
                    if "energy_threshold" in vad:
                        pipeline.vad_config.energy_threshold = float(vad["energy_threshold"])
                    if "silence_duration_ms" in vad:
                        pipeline.vad_config.silence_duration_ms = int(vad["silence_duration_ms"])
                    if "min_speech_ms" in vad:
                        pipeline.vad_config.min_speech_ms = int(vad["min_speech_ms"])
                await send({
                    "type": "config_updated",
                    "stt_backend": pipeline.stt_backend,
                    "tts": want_tts,
                    "vad_config": {
                        "energy_threshold": pipeline.vad_config.energy_threshold,
                        "silence_duration_ms": pipeline.vad_config.silence_duration_ms,
                        "min_speech_ms": pipeline.vad_config.min_speech_ms,
                    },
                })

    except WebSocketDisconnect:
        pass
    finally:
        pipeline.reset()
        _voice_clients.discard(ws)


# ─── Dispatch timer (background task) ───
async def _dispatch_loop():
    """Periodically check if queued task should be dispatched."""
    while True:
        await asyncio.sleep(2)
        task = _proxy.check_dispatch()
        if task:
            # Integration hook: external OpenClaw bridge should consume this event and
            # send task to main session (sessions_send). For now, broadcast and log.
            print(f"[DISPATCH] Ready for main agent: {task[:120]}")
            await _broadcast({"type": "dispatch_ready", "task": task})


@app.on_event("startup")
async def _startup():
    asyncio.create_task(_dispatch_loop())
