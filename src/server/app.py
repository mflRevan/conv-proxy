"""
FastAPI application — serves the Svelte frontend,
REST API for sessions/agents, and WebSocket for live events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import AppConfig
from ..gateway.client import GatewayClient, GatewayConfig, ConnectionState, AgentEvent
from ..gateway.events import EventManager

logger = logging.getLogger("server")

# ---------------------------------------------------------------------------
# Globals (set during lifespan)
# ---------------------------------------------------------------------------

config: AppConfig = AppConfig()
gateway: Optional[GatewayClient] = None
events: EventManager = EventManager()
_gateway_task: Optional[asyncio.Task] = None
_dispatch_task: Optional[asyncio.Task] = None
_frontend_clients: set[WebSocket] = set()

# Voice components (lazy-loaded)
_pipeline = None
_tts = None
_stt = None


# ---------------------------------------------------------------------------
# Markdown stripping for TTS
# ---------------------------------------------------------------------------

_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_MD_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```", re.MULTILINE)
_MD_INLINE_CODE_RE = re.compile(r"`([^`]+)`")


def strip_markdown(text: str) -> str:
    if not text:
        return ""
    s = _MD_CODE_BLOCK_RE.sub(" ", text)
    s = _MD_LINK_RE.sub(r"\1", s)
    s = _MD_INLINE_CODE_RE.sub(r"\1", s)
    s = re.sub(r"^#{1,6}\s*", "", s, flags=re.MULTILINE)
    s = re.sub(r"^[\-*+]\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"^\d+\.\s+", "", s, flags=re.MULTILINE)
    s = re.sub(r"^>\s?", "", s, flags=re.MULTILINE)
    s = s.replace("**", "").replace("__", "").replace("*", "").replace("_", "")
    s = s.replace("~~", "")
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------------------
# Frontend WS broadcast
# ---------------------------------------------------------------------------

async def broadcast(msg: dict):
    """Send a message to all connected frontend WebSockets."""
    if not _frontend_clients:
        return
    data = json.dumps(msg)
    dead = set()
    for ws in _frontend_clients:
        try:
            await ws.send_text(data)
        except Exception:
            dead.add(ws)
    _frontend_clients.difference_update(dead)


# ---------------------------------------------------------------------------
# Gateway event handler
# ---------------------------------------------------------------------------

async def on_gateway_event(event: AgentEvent):
    """Route gateway events to the event manager."""
    await events.handle_event(event)

    planner = _get_planner()
    if not planner:
        return

    state = events.sessions.get(event.session_key)
    if not state:
        return

    current_task = ""
    if state.current_run and state.current_run.tool_calls:
        for tc in reversed(state.current_run.tool_calls):
            if tc.status == "running":
                current_task = tc.name
                break

    turns = []
    if state.current_run and state.current_run.assistant_chunks:
        turns.append({
            "role": "assistant",
            "content": "".join(state.current_run.assistant_chunks)[-1200:],
        })
    if state.last_run and state.last_run.final_text:
        turns.append({
            "role": "assistant",
            "content": state.last_run.final_text[-1200:],
        })

    just_finished = event.stream == "lifecycle" and event.data.get("phase") in ("run_end", "run_complete")
    completion_brief = state.last_run.final_text[:500] if state.last_run and state.last_run.final_text else ""

    planner.update_agent_context(
        status=state.agent_status,
        current_task=current_task,
        turns=turns,
        compressed_context="",
        just_finished=just_finished,
        completion_brief=completion_brief,
    )


async def on_gateway_state_change(state: ConnectionState):
    """Broadcast gateway connection state to frontends."""
    await broadcast({
        "type": "gateway_status",
        "state": state.value,
        "ts": time.time(),
    })


# ---------------------------------------------------------------------------
# History context helpers
# ---------------------------------------------------------------------------

async def _select_primary_session_key() -> Optional[str]:
    if not gateway or not gateway.connected:
        return None
    try:
        sessions = await gateway.list_sessions()
    except Exception:
        return None
    for s in sessions:
        if s.raw.get("kind") in ("main", "channel"):
            return s.key
    return sessions[0].key if sessions else None


def _format_history_lines(messages: list[dict]) -> list[str]:
    lines: list[str] = []
    for m in messages:
        role = m.get("role", "?")
        content = m.get("content", m.get("text", ""))
        if isinstance(content, list):
            # flatten content list to text-only
            parts = []
            for c in content:
                if isinstance(c, dict):
                    parts.append(c.get("text", c.get("content", "")))
                elif isinstance(c, str):
                    parts.append(c)
            content = "\n".join([p for p in parts if p])
        if not isinstance(content, str):
            content = str(content)
        content = content.strip()
        if not content:
            continue
        lines.append(f"[{role}] {content}")
    return lines


async def _build_main_history_context() -> tuple[list[str], list[str]]:
    """Return (text_only_lines, full_res_lines) for main agent history."""
    session_key = await _select_primary_session_key()
    if not session_key:
        return [], []
    try:
        raw = await gateway.get_history(session_key, limit=max(config.main_history_length, config.main_history_full_count) + 5)
    except Exception:
        return [], []

    # Normalize ordering oldest->newest
    messages = list(raw or [])
    if messages and isinstance(messages[0], dict) and messages[0].get("timestamp"):
        messages.sort(key=lambda m: m.get("timestamp", 0))
    else:
        messages = list(reversed(messages))

    # Filter user/assistant only for text-only
    filtered = [m for m in messages if m.get("role") in ("user", "assistant")]
    text_only = _format_history_lines(filtered[-config.main_history_length:])
    full_res = _format_history_lines(filtered[-config.main_history_full_count:])

    # Attach last-run tool calls to full-res section (if available)
    if session_key in events.sessions:
        tool_calls = events.get_tool_calls(session_key)
        if tool_calls:
            full_res.append("[tools] Recent tool activity:")
            for tc in tool_calls[-6:]:
                name = tc.get("name", "tool")
                args = (tc.get("arguments", "") or "")[:500]
                res = (tc.get("result", "") or "")[:1000]
                if args:
                    full_res.append(f"- {name} args: {args}")
                if res:
                    full_res.append(f"- {name} result: {res}")

    return text_only, full_res


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global config, gateway, _gateway_task, _dispatch_task, _pipeline, _tts, _stt

    config = AppConfig.from_env()
    logger.info(f"Starting conv-proxy on {config.host}:{config.port}")

    # Set up event manager broadcast
    events.set_broadcast(broadcast)

    # Initialize gateway client
    if config.gateway_token:
        gw_config = GatewayConfig(
            url=config.gateway_url,
            token=config.gateway_token,
            origin=config.gateway_origin,
        )
        gateway = GatewayClient(gw_config)
        gateway.on_event = on_gateway_event
        gateway.on_state_change = on_gateway_state_change
        _gateway_task = asyncio.create_task(gateway.connect())
        logger.info(f"Gateway client connecting to {config.gateway_url}")
    else:
        logger.warning("No GATEWAY_TOKEN set — gateway features disabled")

    # Ensure HF token is visible to downstream libs
    if config.hf_token:
        os.environ.setdefault("HUGGINGFACE_HUB_TOKEN", config.hf_token)
        os.environ.setdefault("HF_TOKEN", config.hf_token)

    # Lazy-load voice pipeline
    try:
        from ..voice.pipeline import VoicePipeline, VADConfig
        from ..voice.wakeword import WakewordDetector

        vad_config = VADConfig()
        wakeword = WakewordDetector(
            enabled=config.wakeword_enabled,
            threshold=config.wakeword_threshold,
        )
        _pipeline = VoicePipeline(
            stt_backend=config.stt_engine,
            vad_config=vad_config,
            wakeword=wakeword,
            wakeword_active_window_s=config.wakeword_active_window_s,
        )
        logger.info("Voice pipeline initialized")
    except Exception as e:
        logger.warning(f"Voice pipeline not available: {e}")

    # Lazy-load STT
    try:
        from ..stt.engine import create_stt
        if config.stt_engine == "browser":
            _stt = None
        else:
            _stt = create_stt(config.stt_engine)
        logger.info(f"STT engine: {config.stt_engine}")
    except Exception as e:
        logger.warning(f"STT not available: {e}")

    # Lazy-load TTS
    if config.tts_enabled:
        try:
            from ..tts.kokoro_streaming import KokoroStreamingTTS
            _tts = KokoroStreamingTTS()
            logger.info("TTS engine: kokoro")
        except Exception as e:
            logger.warning(f"TTS not available: {e}")

    # Start dispatch loop
    global _dispatch_task
    _dispatch_task = asyncio.create_task(dispatch_loop())

    yield

    # Shutdown
    if gateway:
        await gateway.disconnect()
    if _dispatch_task:
        _dispatch_task.cancel()
        try:
            await _dispatch_task
        except (asyncio.CancelledError, Exception):
            pass
    if _gateway_task:
        _gateway_task.cancel()
        try:
            await _gateway_task
        except (asyncio.CancelledError, Exception):
            pass
    logger.info("Shutdown complete")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent.parent
DIST = ROOT / "frontend" / "dist"

app = FastAPI(lifespan=lifespan)


# ---------------------------------------------------------------------------
# REST API: Gateway
# ---------------------------------------------------------------------------

@app.get("/api/status")
async def api_status():
    return {
        "ok": True,
        "gateway": {
            "connected": gateway.connected if gateway else False,
            "state": gateway.state.value if gateway else "disabled",
            "server": gateway.server_info if gateway else {},
        },
        "voice": {
            "pipeline": _pipeline is not None,
            "stt": _stt is not None,
            "tts": _tts is not None,
        },
    }


@app.get("/api/sessions")
async def api_sessions():
    if not gateway or not gateway.connected:
        return JSONResponse({"error": "Gateway not connected"}, status_code=503)
    try:
        sessions = await gateway.list_sessions()
        return {
            "sessions": [
                {
                    "key": s.key,
                    "kind": s.kind,
                    "displayName": s.display_name,
                    "agentId": s.agent_id,
                    "sessionId": s.session_id,
                    "model": s.model,
                    "modelProvider": s.model_provider,
                    "updatedAt": s.updated_at,
                    "inputTokens": s.input_tokens,
                    "outputTokens": s.output_tokens,
                }
                for s in sessions
            ]
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/agents")
async def api_agents():
    if not gateway or not gateway.connected:
        return JSONResponse({"error": "Gateway not connected"}, status_code=503)
    try:
        agents = await gateway.list_agents()
        return {
            "agents": [{"id": a.id, "name": a.name} for a in agents]
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/abort")
async def api_abort(body: dict):
    if not gateway or not gateway.connected:
        return JSONResponse({"error": "Gateway not connected"}, status_code=503)
    session_key = body.get("sessionKey", "")
    if not session_key:
        return JSONResponse({"error": "sessionKey required"}, status_code=400)
    try:
        result = await gateway.abort_run(session_key)
        return {"ok": True, "result": result}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/cot/{session_key:path}")
async def api_cot(session_key: str):
    return {
        "cot": events.get_cot_text(session_key),
        "toolCalls": events.get_tool_calls(session_key),
    }


@app.get("/api/session-state/{session_key:path}")
async def api_session_state(session_key: str):
    state = events.sessions.get(session_key)
    if not state:
        return {"status": "unknown", "currentRun": None}
    return {
        "status": state.agent_status,
        "lastEventAt": state.last_event_at,
        "currentRun": {
            "runId": state.current_run.run_id,
            "status": state.current_run.status,
            "toolCount": len(state.current_run.tool_calls),
            "assistantLength": len("".join(state.current_run.assistant_chunks)),
            "cotLength": len("".join(state.current_run.cot_chunks)),
        } if state.current_run else None,
    }


# ---------------------------------------------------------------------------
# REST API: Settings (runtime config updates)
# ---------------------------------------------------------------------------

@app.post("/api/settings")
async def api_settings(body: dict):
    """Update runtime settings (gateway token, voice config, etc.)."""
    global gateway, _gateway_task

    changed = False

    # Gateway update
    gateway_url = body.get("gatewayUrl", config.gateway_url)
    gateway_origin = body.get("gatewayOrigin", config.gateway_origin)
    gateway_token = body.get("gatewayToken", config.gateway_token)
    if gateway_url != config.gateway_url or gateway_origin != config.gateway_origin or gateway_token != config.gateway_token:
        config.gateway_url = gateway_url
        config.gateway_origin = gateway_origin
        config.gateway_token = gateway_token
        # Reconnect gateway
        if gateway:
            await gateway.disconnect()
            if _gateway_task:
                _gateway_task.cancel()

        gw_config = GatewayConfig(
            url=config.gateway_url,
            token=config.gateway_token,
            origin=config.gateway_origin,
        )
        gateway = GatewayClient(gw_config)
        gateway.on_event = on_gateway_event
        gateway.on_state_change = on_gateway_state_change
        _gateway_task = asyncio.create_task(gateway.connect())
        changed = True

    # Proxy agent settings
    planner = _get_planner()
    if planner:
        if "proxyModel" in body and body["proxyModel"]:
            planner.engine.model = body["proxyModel"]
            config.proxy_model = body["proxyModel"]
            changed = True
        if "proxyTemperature" in body:
            try:
                planner.engine.temperature = float(body["proxyTemperature"])
                changed = True
            except Exception:
                pass
        if "proxyMaxTokens" in body:
            try:
                planner.engine.max_tokens = int(body["proxyMaxTokens"])
                changed = True
            except Exception:
                pass
        if "historyLength" in body:
            try:
                planner.max_history_pairs = max(1, int(body["historyLength"]))
                changed = True
            except Exception:
                pass
        if "mainHistoryLength" in body:
            try:
                config.main_history_length = max(1, int(body["mainHistoryLength"]))
                changed = True
            except Exception:
                pass
        if "mainHistoryFullCount" in body:
            try:
                config.main_history_full_count = max(1, int(body["mainHistoryFullCount"]))
                changed = True
            except Exception:
                pass
        if "compressedContext" in body:
            planner.state.compressed_context = body["compressedContext"] or ""
            changed = True

    # Voice settings
    if _pipeline:
        if "vadThreshold" in body:
            try:
                _pipeline.vad_config.energy_threshold = float(body["vadThreshold"])
                changed = True
            except Exception:
                pass
        if "silenceDurationMs" in body:
            try:
                _pipeline.vad_config.silence_duration_ms = int(body["silenceDurationMs"])
                changed = True
            except Exception:
                pass
        if "minSpeechMs" in body:
            try:
                _pipeline.vad_config.min_speech_ms = int(body["minSpeechMs"])
                changed = True
            except Exception:
                pass
        if "wakewordEnabled" in body:
            _pipeline.wakeword.enabled = bool(body["wakewordEnabled"])
            changed = True
        if "wakewordThreshold" in body:
            _pipeline.wakeword.threshold = float(body["wakewordThreshold"])
            changed = True
        if "wakewordActiveWindowMs" in body:
            _pipeline.wakeword_active_window_s = max(1.0, float(body["wakewordActiveWindowMs"]) / 1000.0)
            changed = True

    if "sttBackend" in body:
        config.stt_engine = body["sttBackend"]
        if _pipeline:
            _pipeline.stt_backend = config.stt_engine
        try:
            from ..stt.engine import create_stt
            globals()["_stt"] = None if config.stt_engine == "browser" else create_stt(config.stt_engine)
            changed = True
        except Exception:
            pass

    if "ttsEnabled" in body:
        config.tts_enabled = bool(body["ttsEnabled"])
        changed = True

    return {"ok": True, "changed": changed}







# ---------------------------------------------------------------------------
# Planner agent (proxy controller)
# ---------------------------------------------------------------------------

_planner = None
_planner_lock = asyncio.Lock()



def _get_planner():
    global _planner
    if _planner is None:
        try:
            from ..proxy.controller import ProxyController
            from ..llm.openrouter_engine import OpenRouterEngine

            if not config.openrouter_api_key:
                raise ValueError("OPENROUTER_API_KEY not set")

            engine = OpenRouterEngine(
                api_key=config.openrouter_api_key,
                model=config.proxy_model,
            )
            _planner = ProxyController(engine=engine)
        except Exception as e:
            logger.error(f"Planner init failed: {e}")
    return _planner


async def stream_proxy_message(message: str):
    planner = _get_planner()
    if not planner:
        await broadcast({"type": "proxy_error", "message": "Planner not available"})
        return

    # Refresh main agent history context before each proxy turn
    try:
        history_text, history_full = await _build_main_history_context()
        planner.update_agent_context(history_text=history_text, history_full=history_full)
        stats = planner.get_context_stats()
        await broadcast({
            "type": "context_size",
            "messages": len(history_text),
            "fullMessages": len(history_full),
            "chars": stats.get("total_chars", 0),
            "promptChars": stats.get("prompt_chars", 0),
            "conversationChars": stats.get("conversation_chars", 0),
            "proxyMdChars": stats.get("proxy_md_chars", 0),
            "compressedChars": stats.get("compressed_chars", 0),
            "historyTextChars": stats.get("history_text_chars", 0),
            "historyFullChars": stats.get("history_full_chars", 0),
            "liveTurnChars": stats.get("live_turn_chars", 0),
            "scratchpadChars": stats.get("scratchpad_chars", 0),
            "queuedChars": stats.get("queued_chars", 0),
        })
    except Exception:
        pass

    async with _planner_lock:
        await _stream_proxy_message_locked(planner, message)


async def _stream_proxy_message_locked(planner, message: str):
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    cancel_event = _pipeline.start_response() if _pipeline else None

    def runner():
        try:
            for delta in planner.process_message_stream(message, cancel_event=cancel_event):
                asyncio.run_coroutine_threadsafe(queue.put(delta), loop)
        finally:
            asyncio.run_coroutine_threadsafe(queue.put({"type": "__done__"}), loop)

    import threading
    threading.Thread(target=runner, daemon=True).start()

    full_reply = ""
    await broadcast({"type": "state", "state": "processing"})

    while True:
        delta = await queue.get()
        if delta.get("type") == "__done__":
            break
        dt = delta.get("type")

        if dt == "content":
            text = delta.get("text", "")
            full_reply += text
            await broadcast({"type": "proxy_delta", "delta": text})
        elif dt == "reasoning":
            await broadcast({"type": "proxy_reasoning", "delta": delta.get("text", "")})
        elif dt == "action":
            await broadcast({
                "type": "proxy_action",
                "action": delta.get("action", ""),
                "task": delta.get("task", ""),
                "scratchpad": planner.state.scratchpad_task,
                "queued": planner.state.queued_task,
                "dispatchDelay": planner.state.dispatch_delay,
            })
        elif dt == "done":
            await broadcast({
                "type": "proxy_done",
                "message": full_reply,
                "scratchpad": planner.state.scratchpad_task,
                "queued": planner.state.queued_task,
                "dispatchDelay": planner.state.dispatch_delay,
            })
        elif dt == "cancelled":
            await broadcast({"type": "proxy_cancelled"})
            return
        elif dt == "error":
            await broadcast({"type": "proxy_error", "message": delta.get("message", "")})
            return

    if _pipeline and config.tts_enabled and full_reply:
        await broadcast({"type": "state", "state": "speaking"})
        _pipeline.begin_speaking()
        for b64, sr, first in _pipeline.synthesize_streaming(strip_markdown(full_reply)):
            await broadcast({"type": "audio", "content": b64, "sample_rate": sr, "first": first})
        _pipeline.finish_response()
        await broadcast({"type": "state", "state": "idle"})
    else:
        if _pipeline:
            _pipeline.finish_response()
        await broadcast({"type": "state", "state": "idle"})

async def dispatch_loop():
    while True:
        await asyncio.sleep(1.0)
        if not config.openrouter_api_key:
            continue
        planner = _get_planner()
        if not planner:
            continue

        task = planner.check_dispatch()
        if not task:
            continue

        if not gateway or not gateway.connected:
            planner.state.queued_task = task
            await broadcast({"type": "proxy_dispatch_error", "error": "Gateway not connected"})
            continue

        try:
            sessions = await gateway.list_sessions()
            target = None
            for s in sessions:
                if s.raw.get("kind") in ("main", "channel"):
                    target = s.key
                    break
            if not target and sessions:
                target = sessions[0].key
            if not target:
                planner.state.queued_task = task
                await broadcast({"type": "proxy_dispatch_error", "error": "No active session"})
                continue
            await gateway.send_message(target, task)
            await broadcast({"type": "proxy_dispatched", "task": task})
        except Exception as e:
            planner.state.queued_task = task
            await broadcast({"type": "proxy_dispatch_error", "error": str(e)})




@app.post("/api/plan/message")
async def api_plan_message(body: dict):
    """Send a message to the planner agent (streamed via WebSocket)."""
    message = body.get("message", "")
    if not message:
        return JSONResponse({"error": "message required"}, status_code=400)

    planner = _get_planner()
    if not planner:
        return JSONResponse({"error": "Planner not available (check OPENROUTER_API_KEY)"}, status_code=503)

    asyncio.create_task(stream_proxy_message(message))
    return {"ok": True}


@app.get("/api/plan/scratchpad")
async def api_plan_scratchpad():
    """Get the current planner scratchpad."""
    planner = _get_planner()
    if not planner:
        return {"scratchpad": "", "queued": ""}
    return {
        "scratchpad": planner.state.scratchpad_task,
        "queued": planner.state.queued_task,
    }


@app.post("/api/plan/dispatch")
async def api_plan_dispatch(body: dict):
    """Dispatch the queued task to the selected session."""
    if not gateway or not gateway.connected:
        return JSONResponse({"error": "Gateway not connected"}, status_code=503)

    planner = _get_planner()
    task_text = ""
    if planner and planner.state.queued_task:
        task_text = planner.state.queued_task
    elif planner and planner.state.scratchpad_task:
        task_text = planner.state.scratchpad_task

    if not task_text:
        task_text = body.get("task", "")

    session_key = body.get("sessionKey", "")
    if not session_key or not task_text:
        return JSONResponse({"error": "sessionKey and task required"}, status_code=400)

    try:
        result = await gateway.send_message(session_key, task_text)
        # Clear the planner state
        if planner:
            planner.state.queued_task = ""
            planner.state.scratchpad_task = ""
        return {"ok": True, "dispatched": task_text[:200], "result": result}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# WebSocket: Frontend events
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def ws_frontend(ws: WebSocket):
    await ws.accept()
    _frontend_clients.add(ws)

    planner = _get_planner()

    # Send initial state
    try:
        await ws.send_json({
            "type": "init",
            "gateway": {
                "connected": gateway.connected if gateway else False,
                "state": gateway.state.value if gateway else "disabled",
            },
            "proxyModel": config.proxy_model,
            "scratchpad": planner.state.scratchpad_task if planner else "",
            "queued": planner.state.queued_task if planner else "",
        })
    except Exception:
        pass

    try:
        async for raw in ws.iter_text():
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")

            if msg_type == "audio_chunk":
                if _pipeline:
                    import base64
                    import numpy as np

                    audio_b64 = msg.get("data", "")
                    if audio_b64:
                        pcm16 = np.frombuffer(base64.b64decode(audio_b64), dtype=np.int16)
                        pcm = (pcm16.astype(np.float32)) / 32768.0
                        result = _pipeline.process_audio_chunk(pcm)
                        if result:
                            await ws.send_json({"type": "vad", "event": result})
                        if result == "speech_end":
                            text = ""
                            if _stt:
                                audio = _pipeline.get_audio_buffer()
                                _pipeline._audio_buffer.clear()
                                try:
                                    transcription = await asyncio.to_thread(
                                        _stt.transcribe, audio, sample_rate=_pipeline.vad_config.sample_rate
                                    )
                                    text = transcription.text.strip()
                                except Exception:
                                    text = ""
                            if text:
                                await ws.send_json({"type": "transcription", "text": text, "final": True})
                                asyncio.create_task(stream_proxy_message(text))

            elif msg_type == "proxy_message":
                text = msg.get("message", "")
                if text:
                    asyncio.create_task(stream_proxy_message(text))

            elif msg_type == "config":
                if _pipeline:
                    vad = msg.get("vad") or {}
                    if "energy_threshold" in vad:
                        _pipeline.vad_config.energy_threshold = float(vad["energy_threshold"])
                    if "silence_duration_ms" in vad:
                        _pipeline.vad_config.silence_duration_ms = int(vad["silence_duration_ms"])
                    if "min_speech_ms" in vad:
                        _pipeline.vad_config.min_speech_ms = int(vad["min_speech_ms"])

                    ww = msg.get("wakeword") or {}
                    if "enabled" in ww:
                        _pipeline.wakeword.enabled = bool(ww["enabled"])
                    if "threshold" in ww:
                        _pipeline.wakeword.threshold = float(ww["threshold"])
                    if "active_window_ms" in ww:
                        _pipeline.wakeword_active_window_s = max(1.0, float(ww["active_window_ms"]) / 1000.0)

                if "stt_backend" in msg:
                    config.stt_engine = msg["stt_backend"]
                    if _pipeline:
                        _pipeline.stt_backend = config.stt_engine
                    try:
                        from ..stt.engine import create_stt
                        globals()["_stt"] = None if config.stt_engine == "browser" else create_stt(config.stt_engine)
                    except Exception:
                        pass
                if "tts" in msg:
                    config.tts_enabled = bool(msg["tts"])

            elif msg_type == "cancel":
                if _pipeline:
                    _pipeline.cancel_output()
                    await ws.send_json({"type": "state", "state": "idle"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Frontend WS error: {e}")
    finally:
        _frontend_clients.discard(ws)


# ---------------------------------------------------------------------------
# Static files (Svelte frontend)
# ---------------------------------------------------------------------------

if DIST.exists():
    @app.get("/")
    async def index():
        return FileResponse(DIST / "index.html")

    app.mount("/assets", StaticFiles(directory=str(DIST / "assets")), name="static")

    @app.get("/{path:path}")
    async def catch_all(path: str):
        file = DIST / path
        if file.exists() and file.is_file():
            return FileResponse(file)
        return FileResponse(DIST / "index.html")
