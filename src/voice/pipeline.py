"""
Real-time voice pipeline for conv-proxy.

Manages the full cycle:
  mic audio → VAD → STT → LLM (streaming) → TTS → audio out

With barge-in: user speech during TTS → cancel LLM + TTS immediately.

This module handles the server-side state machine. The browser handles
audio capture/playback and sends chunks via WebSocket.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Optional

import numpy as np
import soundfile as sf

from src.stt.engine import create_stt
from src.tts.kokoro_streaming import KokoroStreamingTTS
from src.voice.wakeword import WakewordDetector

log = logging.getLogger(__name__)


class PipelineState(Enum):
    IDLE = auto()        # Waiting for user speech
    LISTENING = auto()   # User is speaking (VAD active)
    PROCESSING = auto()  # STT → LLM in progress
    SPEAKING = auto()    # TTS audio being sent to client
    CANCELLED = auto()   # Interrupted, resetting


@dataclass
class VADConfig:
    """Server-side VAD config (for when audio is streamed as raw PCM)."""
    energy_threshold: float = 0.015    # RMS threshold for speech detection
    silence_duration_ms: int = 800     # ms of silence to end utterance
    speech_pad_ms: int = 300           # padding before/after speech
    min_speech_ms: int = 250           # minimum speech duration to process
    sample_rate: int = 16000


@dataclass
class VoicePipeline:
    """
    Server-side voice pipeline state machine.
    
    Manages turn-taking, barge-in, and stream cancellation.
    The actual audio capture happens in the browser.
    """
    stt_backend: str = "moonshine-tiny"
    tts_engine: Optional[KokoroStreamingTTS] = None
    vad_config: VADConfig = field(default_factory=VADConfig)
    
    # State
    state: PipelineState = PipelineState.IDLE
    _audio_buffer: list[np.ndarray] = field(default_factory=list)
    _silence_start: float = 0.0
    _speech_start: float = 0.0
    _cancel_event: Optional[threading.Event] = None
    _tts_cancel_event: Optional[threading.Event] = None

    # Wakeword gate
    wakeword: WakewordDetector = field(default_factory=WakewordDetector)
    _wakeword_active_until: float = 0.0
    wakeword_active_window_s: float = 10.0

    # Callbacks (set by WebSocket handler)
    on_state_change: Optional[Callable[[PipelineState], None]] = None
    on_transcription: Optional[Callable[[str, bool], None]] = None  # (text, is_final)
    on_vad_event: Optional[Callable[[str], None]] = None  # speech_start, speech_end, wakeword

    def __post_init__(self):
        if self.tts_engine is None:
            self.tts_engine = KokoroStreamingTTS()
        self._cancel_event = threading.Event()
        self._tts_cancel_event = threading.Event()

    def _set_state(self, new_state: PipelineState):
        old = self.state
        self.state = new_state
        if old != new_state:
            log.debug(f"Pipeline: {old.name} → {new_state.name}")
            if self.on_state_change:
                self.on_state_change(new_state)

    def process_audio_chunk(self, pcm_data: np.ndarray) -> Optional[str]:
        """
        Process an incoming audio chunk from the browser.
        
        Returns:
        - None: still accumulating / no action needed
        - "speech_start": VAD detected speech onset
        - "speech_end": silence after speech → ready for STT
        - "barge_in": user spoke during TTS → cancel output
        
        Audio should be float32, mono, at vad_config.sample_rate.
        """
        rms = np.sqrt(np.mean(pcm_data ** 2))
        now = time.monotonic()
        is_speech = rms > self.vad_config.energy_threshold

        # ─── Barge-in detection ───
        if self.state == PipelineState.SPEAKING and is_speech:
            self.cancel_output()
            self._audio_buffer = [pcm_data]
            self._speech_start = now
            self._silence_start = 0.0
            self._set_state(PipelineState.LISTENING)
            if self.on_vad_event:
                self.on_vad_event("barge_in")
            return "barge_in"

        # ─── Wakeword gate in IDLE ───
        if self.state == PipelineState.IDLE and self.wakeword.enabled:
            armed = now < self._wakeword_active_until
            if not armed and self.wakeword.detect(pcm_data, sample_rate=self.vad_config.sample_rate):
                self._wakeword_active_until = now + self.wakeword_active_window_s
                if self.on_vad_event:
                    self.on_vad_event("wakeword")
                armed = True
            if not armed:
                return None

        # ─── IDLE → LISTENING ───
        if self.state == PipelineState.IDLE and is_speech:
            self._audio_buffer = [pcm_data]
            self._speech_start = now
            self._silence_start = 0.0
            self._set_state(PipelineState.LISTENING)
            if self.on_vad_event:
                self.on_vad_event("speech_start")
            return "speech_start"

        # ─── LISTENING ───
        if self.state == PipelineState.LISTENING:
            self._audio_buffer.append(pcm_data)

            if is_speech:
                self._silence_start = 0.0
            else:
                if self._silence_start == 0.0:
                    self._silence_start = now
                
                silence_ms = (now - self._silence_start) * 1000
                speech_ms = (now - self._speech_start) * 1000

                if silence_ms >= self.vad_config.silence_duration_ms:
                    if speech_ms >= self.vad_config.min_speech_ms:
                        self._set_state(PipelineState.PROCESSING)
                        self._wakeword_active_until = now + self.wakeword_active_window_s
                        if self.on_vad_event:
                            self.on_vad_event("speech_end")
                        return "speech_end"
                    else:
                        # Too short, reset
                        self._audio_buffer.clear()
                        self._set_state(PipelineState.IDLE)
                        return None

        return None

    def get_audio_buffer(self) -> np.ndarray:
        """Get accumulated audio buffer as single array."""
        if not self._audio_buffer:
            return np.array([], dtype=np.float32)
        return np.concatenate(self._audio_buffer)

    def transcribe_buffer(self) -> str:
        """Run STT on the accumulated audio buffer."""
        audio = self.get_audio_buffer()
        if audio.size == 0:
            return ""

        try:
            stt = create_stt(self.stt_backend)
            result = stt.transcribe(audio, sample_rate=self.vad_config.sample_rate)
            return result.text.strip()
        except Exception as e:
            log.exception("STT transcription failed: %s", e)
            return ""
        finally:
            self._audio_buffer.clear()

    def start_response(self) -> threading.Event:
        """Mark pipeline as processing/speaking. Returns cancel event."""
        self._cancel_event = threading.Event()
        self._tts_cancel_event = threading.Event()
        return self._cancel_event

    def begin_speaking(self):
        """Transition to SPEAKING state (TTS started)."""
        self._set_state(PipelineState.SPEAKING)

    def finish_response(self):
        """Response complete, return to IDLE."""
        self._audio_buffer.clear()
        self._set_state(PipelineState.IDLE)

    def cancel_output(self):
        """Cancel active LLM stream and TTS."""
        if self._cancel_event:
            self._cancel_event.set()
        if self._tts_cancel_event:
            self._tts_cancel_event.set()
        log.debug("Pipeline: output cancelled")

    def reset(self):
        """Full reset."""
        self.cancel_output()
        self._audio_buffer.clear()
        self._silence_start = 0.0
        self._speech_start = 0.0
        self._wakeword_active_until = 0.0
        self._set_state(PipelineState.IDLE)

    @property
    def is_cancellable(self) -> bool:
        return self.state in (PipelineState.PROCESSING, PipelineState.SPEAKING)

    def synthesize_streaming(self, text: str):
        """
        Yield TTS audio chunks (PCM16 base64) with cancellation support.
        Yields: (base64_pcm16, sample_rate, is_first_chunk)
        """
        if not text or not self.tts_engine:
            return

        self._tts_cancel_event = threading.Event()
        first = True
        
        for audio_chunk in self.tts_engine.synthesize_streaming(text, strategy="sentence"):
            if self._tts_cancel_event.is_set():
                return
            
            if audio_chunk.size == 0:
                continue
            
            audio_clipped = np.clip(audio_chunk, -1.0, 1.0)
            pcm16 = (audio_clipped * 32767).astype(np.int16)
            b64 = base64.b64encode(pcm16.tobytes()).decode("utf-8")
            
            yield b64, self.tts_engine.sample_rate, first
            first = False
