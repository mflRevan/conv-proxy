const BASE = import.meta.env.DEV ? 'http://localhost:37374' : '';
const WS_BASE = import.meta.env.DEV ? 'ws://localhost:37374' : `ws://${window.location.host}`;

import { messages, status, sttBackends, selectedStt, isGenerating, nextId } from '../stores/chat';
import type { ChatMessage, ToolCall } from '../types/chat';
import { get } from 'svelte/store';

let ws: WebSocket | null = null;
let wsReady = false;
let resolveStream: (() => void) | null = null;
let currentMsg: ChatMessage | null = null;
let streamStart = 0;

// --- WebSocket ---
export function connect() {
  try {
    ws = new WebSocket(`${WS_BASE}/ws/chat`);
  } catch {
    status.update(s => ({ ...s, connected: false }));
    setTimeout(connect, 3000);
    return;
  }

  ws.onopen = () => {
    wsReady = true;
    status.update(s => ({ ...s, connected: true }));
  };
  ws.onclose = () => {
    wsReady = false;
    status.update(s => ({ ...s, connected: false }));
    setTimeout(connect, 3000);
  };
  ws.onerror = () => {
    wsReady = false;
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    handleWsMessage(data);
  };
}

function handleWsMessage(data: any) {
  if (data.type === 'status') return;

  if (data.type === 'text') {
    if (!currentMsg) {
      currentMsg = { id: nextId(), role: 'assistant', text: '', timestamp: Date.now() };
      streamStart = performance.now();
      messages.update(m => [...m, currentMsg!]);
    }
    if (currentMsg.ttft === undefined) {
      currentMsg.ttft = performance.now() - streamStart;
    }
    currentMsg.text += data.content;
    messages.update(m => [...m]); // trigger reactivity
  }

  if (data.type === 'thinking') {
    if (!currentMsg) {
      currentMsg = { id: nextId(), role: 'assistant', text: '', timestamp: Date.now() };
      streamStart = performance.now();
      messages.update(m => [...m, currentMsg!]);
    }
    currentMsg.thinking = data.content;
    messages.update(m => [...m]);
  }

  if (data.type === 'tool_call') {
    if (currentMsg) {
      if (!currentMsg.toolCalls) currentMsg.toolCalls = [];
      currentMsg.toolCalls.push(data.content);
      messages.update(m => [...m]);
    }
  }

  if (data.type === 'audio') {
    if (currentMsg) {
      if (!currentMsg.audio) currentMsg.audio = [];
      currentMsg.audio.push(data.content);
      currentMsg.sampleRate = data.sample_rate;
      if (data.ttfa_ms && currentMsg.ttft === undefined) {
        currentMsg.ttft = data.ttfa_ms; // repurpose: time to first audio
      }
      playAudioChunk(data.content, data.sample_rate);
    }
  }

  if (data.type === 'done') {
    if (currentMsg) {
      currentMsg.totalMs = performance.now() - streamStart;
      messages.update(m => [...m]);
    }
    currentMsg = null;
    isGenerating.set(false);
    resolveStream?.();
    resolveStream = null;
  }

  if (data.type === 'stt') {
    if (data.text) sendMessage(data.text);
  }
}

// --- HTTP fallback ---
async function sendHttpChat(text: string, tts: boolean): Promise<void> {
  const t0 = performance.now();
  const msg: ChatMessage = { id: nextId(), role: 'assistant', text: '⏳', timestamp: Date.now() };
  messages.update(m => [...m, msg]);

  try {
    const res = await fetch(`${BASE}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, tts })
    });
    const data = await res.json();
    msg.text = data.text || data.error || '';
    msg.thinking = data.thinking;
    msg.toolCalls = data.tool_calls;
    msg.totalMs = performance.now() - t0;
    if (data.audio) {
      msg.audio = data.audio;
      msg.sampleRate = data.sample_rate;
      if (data.ttfa_ms) msg.ttft = data.ttfa_ms;
      data.audio.forEach((c: string) => playAudioChunk(c, data.sample_rate));
    }
    messages.update(m => [...m]);
  } catch (e: any) {
    msg.text = `Error: ${e.message}`;
    messages.update(m => [...m]);
  }
  isGenerating.set(false);
}

// --- Public API ---
export async function sendMessage(text: string, tts = false) {
  if (!text.trim()) return;

  const userMsg: ChatMessage = { id: nextId(), role: 'user', text: text.trim(), timestamp: Date.now() };
  messages.update(m => [...m, userMsg]);
  isGenerating.set(true);

  if (wsReady && ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ message: text.trim(), tts }));
    // Wait for 'done' or timeout after 60s
    await Promise.race([
      new Promise<void>(resolve => { resolveStream = resolve; }),
      new Promise<void>(resolve => setTimeout(() => {
        if (resolveStream) { resolveStream = null; isGenerating.set(false); }
        resolve();
      }, 60000))
    ]);
  } else {
    await sendHttpChat(text.trim(), tts);
  }
}

export async function fetchSttBackends() {
  try {
    const res = await fetch(`${BASE}/api/stt/backends`);
    const data = await res.json();
    sttBackends.set(data.backends || []);
    if (data.default) selectedStt.set(data.default);
  } catch { /* ignore */ }
}

export async function transcribeAudio(wavBuffer: ArrayBuffer, backend: string): Promise<string> {
  const blob = new Blob([wavBuffer], { type: 'audio/wav' });
  const form = new FormData();
  form.append('file', blob, 'audio.wav');
  const res = await fetch(`${BASE}/api/stt/transcribe?stt_backend=${encodeURIComponent(backend)}`, {
    method: 'POST', body: form
  });
  const data = await res.json();
  return data.text || '';
}

// --- Audio playback ---
let audioCtx: AudioContext | null = null;
const audioQueue: { bytes: Uint8Array; sampleRate: number }[] = [];

function playAudioChunk(b64: string, sampleRate: number) {
  if (!b64) return;
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  audioQueue.push({ bytes, sampleRate });
  if (!audioCtx) audioCtx = new AudioContext();
  if (audioQueue.length === 1) playNext();
}

function playNext() {
  if (!audioQueue.length) return;
  const { bytes, sampleRate } = audioQueue[0];
  const buffer = audioCtx!.createBuffer(1, bytes.length / 2, sampleRate);
  const ch = buffer.getChannelData(0);
  const view = new DataView(bytes.buffer);
  for (let i = 0; i < ch.length; i++) ch[i] = view.getInt16(i * 2, true) / 32768;
  const src = audioCtx!.createBufferSource();
  src.buffer = buffer;
  src.connect(audioCtx!.destination);
  src.onended = () => { audioQueue.shift(); playNext(); };
  src.start(0);
}

export function clearMessages() {
  messages.set([]);
}
