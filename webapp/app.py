from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path
from typing import List

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from llm.engine import create_engine
from tts.kokoro_streaming import KokoroStreamingTTS

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def resolve_engine_type() -> str:
    env_choice = os.getenv("ENGINE_TYPE")
    if env_choice:
        return env_choice
    if "--engine" in sys.argv:
        idx = sys.argv.index("--engine")
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    return "audio"


engine_type = resolve_engine_type()
engine = create_engine(engine_type=engine_type)
tts_engine = KokoroStreamingTTS()


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


@app.on_event("startup")
def _startup() -> None:
    engine.start_server()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.websocket("/ws/chat")
async def chat_ws(ws: WebSocket) -> None:
    await ws.accept()
    history: List[dict] = []
    system_prompt = load_system_prompt()
    if system_prompt:
        history.append({"role": "system", "content": system_prompt})

    await ws.send_text(json.dumps({"type": "status", "status": "connected"}))
    try:
        while True:
            raw = await ws.receive_text()
            payload = json.loads(raw)
            text = payload.get("message", "").strip()
            want_tts = bool(payload.get("tts", False))
            if not text:
                continue
            history.append({"role": "user", "content": text})

            response_text = ""
            for chunk in engine.chat_stream(history, max_tokens=512):
                response_text += chunk
                await ws.send_text(json.dumps({"type": "text", "content": chunk}))
            history.append({"role": "assistant", "content": response_text})

            if want_tts and response_text:
                for audio in tts_engine.synthesize_streaming(response_text, strategy="sentence"):
                    encoded = pcm16_base64(audio)
                    await ws.send_text(
                        json.dumps(
                            {
                                "type": "audio",
                                "content": encoded,
                                "sample_rate": tts_engine.sample_rate,
                                "format": "pcm16",
                            }
                        )
                    )
            await ws.send_text(json.dumps({"type": "done"}))
    except WebSocketDisconnect:
        return
