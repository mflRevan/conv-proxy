import { get } from 'svelte/store';
import { connection } from '../stores/connection';
import { conversation, generateMessageId } from '../stores/conversation';
import { audio } from '../stores/audio';
import { agentState } from '../stores/agent';
import { audioPlayer } from './audioPlayer';
import { audioRecorder } from './audioRecorder';

const WS_URL = import.meta.env.DEV ? 'ws://localhost:37374/ws' : `ws://${window.location.host}/ws`;
const BASE_RECONNECT_DELAY = 800;
const MAX_RECONNECT_DELAY = 10000;
const MAX_RECONNECT_ATTEMPTS = 12;

let ws: WebSocket | null = null;
let reconnectTimeout: number | null = null;
let dispatchTimer: number | null = null;

function reconnectDelayMs(attempt: number): number {
  const exp = Math.min(MAX_RECONNECT_DELAY, BASE_RECONNECT_DELAY * Math.pow(2, attempt));
  const jitter = Math.floor(Math.random() * 250);
  return exp + jitter;
}

function clearDispatchCountdown() {
  if (dispatchTimer) {
    clearInterval(dispatchTimer);
    dispatchTimer = null;
  }
  conversation.update(s => ({ ...s, dispatchCountdown: null }));
}

function startDispatchCountdown(seconds = 10) {
  clearDispatchCountdown();
  let remaining = seconds;
  conversation.update(s => ({ ...s, dispatchCountdown: remaining }));
  dispatchTimer = window.setInterval(() => {
    remaining -= 1;
    if (remaining <= 0) {
      clearDispatchCountdown();
      return;
    }
    conversation.update(s => ({ ...s, dispatchCountdown: remaining }));
  }, 1000);
}

export function connect() {
  const connState = get(connection);
  if (connState.ws?.readyState === WebSocket.OPEN || connState.ws?.readyState === WebSocket.CONNECTING) {
    return;
  }

  connection.update(state => ({ ...state, status: 'connecting', gatewayState: 'connecting' }));

  try {
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      connection.update(state => ({
        ...state,
        ws,
        status: 'connected',
        reconnectAttempts: 0,
      }));

      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
        reconnectTimeout = null;
      }

      audioRecorder.start();
    };

    ws.onmessage = (event) => {
      try {
        handleMessage(JSON.parse(event.data));
      } catch (e) {
        console.error('Invalid WS message:', e);
      }
    };

    ws.onerror = () => {
      connection.update(state => ({ ...state, status: 'error' }));
    };

    ws.onclose = () => {
      connection.update(state => ({ ...state, ws: null, status: 'disconnected' }));
      audioRecorder.stop();
      audioPlayer.stop();
      clearDispatchCountdown();

      const s = get(connection);
      if (s.reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        const delay = reconnectDelayMs(s.reconnectAttempts);
        reconnectTimeout = window.setTimeout(() => {
          connection.update(state => ({ ...state, reconnectAttempts: state.reconnectAttempts + 1 }));
          connect();
        }, delay);
      }
    };

    connection.update(state => ({ ...state, ws }));
  } catch (error) {
    console.error('Failed to create WebSocket:', error);
    connection.update(state => ({ ...state, status: 'error' }));
  }
}

function handleMessage(msg: any) {
  switch (msg.type) {
    case 'init':
      connection.update(state => ({
        ...state,
        gatewayState: msg.gateway?.state || state.gatewayState,
        proxyModel: msg.proxyModel || state.proxyModel,
      }));
      conversation.update(state => ({
        ...state,
        taskDraft: msg.scratchpad || state.taskDraft,
        queuedTask: msg.queued || state.queuedTask,
      }));
      break;

    case 'gateway_status':
      connection.update(state => ({ ...state, gatewayState: msg.state || state.gatewayState }));
      break;

    case 'proxy_delta':
      conversation.update(state => ({
        ...state,
        currentResponse: state.currentResponse + (msg.delta || ''),
        isStreaming: true,
      }));
      break;

    case 'proxy_done':
      conversation.update(state => ({
        ...state,
        messages: msg.message ? [...state.messages, {
          id: generateMessageId(),
          role: 'assistant',
          content: msg.message,
          timestamp: Date.now(),
        }] : state.messages,
        currentResponse: '',
        isStreaming: false,
        taskDraft: msg.scratchpad ?? state.taskDraft,
        queuedTask: msg.queued ?? state.queuedTask,
      }));
      break;

    case 'proxy_action':
      if (msg.action === 'queued') {
        startDispatchCountdown(Math.round(msg.dispatchDelay || 10));
      } else if (msg.action === 'buffer_cleared' || msg.action === 'stop') {
        clearDispatchCountdown();
      }
      conversation.update(state => ({
        ...state,
        taskDraft: msg.scratchpad ?? state.taskDraft,
        queuedTask: msg.queued ?? state.queuedTask,
      }));
      break;

    case 'proxy_cancelled':
      conversation.update(state => ({
        ...state,
        currentResponse: '',
        isStreaming: false,
      }));
      break;

    case 'proxy_error':
      conversation.update(state => ({
        ...state,
        messages: [...state.messages, {
          id: generateMessageId(),
          role: 'assistant',
          content: msg.message || 'Proxy error occurred.',
          timestamp: Date.now(),
        }],
        currentResponse: '',
        isStreaming: false,
      }));
      break;

    case 'proxy_dispatched':
      clearDispatchCountdown();
      const dispatchAt = Date.now();
      conversation.update(state => ({
        ...state,
        taskDraft: '',
        queuedTask: '',
        lastDispatchAt: dispatchAt,
      }));
      setTimeout(() => {
        conversation.update(state => ({
          ...state,
          lastDispatchAt: state.lastDispatchAt === dispatchAt ? null : state.lastDispatchAt,
        }));
      }, 1800);
      break;

    case 'proxy_dispatch_error':
      clearDispatchCountdown();
      conversation.update(state => ({
        ...state,
        messages: [...state.messages, {
          id: generateMessageId(),
          role: 'assistant',
          content: `Dispatch error: ${msg.error || 'unknown'}`,
          timestamp: Date.now(),
        }],
      }));
      break;

    case 'assistant_delta':
      agentState.update(s => ({ ...s, status: 'busy', assistantStream: s.assistantStream + (msg.delta || '') }));
      break;

    case 'cot_delta':
      agentState.update(s => ({ ...s, thinking: s.thinking + (msg.delta || '') }));
      break;

    case 'tool_call':
      agentState.update(s => ({
        ...s,
        currentTool: msg.name || s.currentTool,
        currentArgs: msg.arguments || s.currentArgs,
        toolCalls: [...s.toolCalls, { name: msg.name, arguments: msg.arguments, status: 'running' }].slice(-6),
      }));
      break;

    case 'tool_result':
      agentState.update(s => ({
        ...s,
        toolCalls: s.toolCalls.map(tc =>
          tc.name === msg.name && !tc.result ? { ...tc, result: msg.content, status: 'completed' } : tc
        ),
      }));
      break;

    case 'agent_status':
      agentState.update(s => ({
        ...s,
        status: msg.status || s.status,
        lastSummary: msg.status === 'idle' ? s.assistantStream || s.lastSummary : s.lastSummary,
        assistantStream: msg.status === 'idle' ? '' : s.assistantStream,
        thinking: msg.status === 'idle' ? '' : s.thinking,
        currentTool: msg.status === 'idle' ? '' : s.currentTool,
        currentArgs: msg.status === 'idle' ? '' : s.currentArgs,
      }));
      break;

    case 'agent_error':
      agentState.update(s => ({
        ...s,
        status: 'error',
        lastSummary: msg.error || 'Agent error',
      }));
      break;

    case 'chat_message':
      if (msg.role === 'assistant') {
        agentState.update(s => ({
          ...s,
          lastSummary: msg.content || s.lastSummary,
        }));
      }
      break;

    case 'transcription':
      audio.update(state => ({ ...state, currentTranscription: msg.text || '' }));
      if (msg.final && msg.text) {
        conversation.update(state => ({
          ...state,
          messages: [...state.messages, {
            id: generateMessageId(),
            role: 'user',
            content: msg.text,
            timestamp: Date.now(),
          }],
        }));
      }
      break;

    case 'vad':
      if (msg.event === 'speech_start') {
        audio.update(s => ({ ...s, micState: 'listening', isVadActive: true }));
      } else if (msg.event === 'speech_end') {
        audio.update(s => ({ ...s, micState: 'processing', isVadActive: false }));
      } else if (msg.event === 'wakeword') {
        audio.update(s => ({ ...s, wakewordActive: true }));
      }
      break;

    case 'state':
      if (msg.state === 'speaking') {
        audio.update(s => ({ ...s, speakerState: 'speaking' }));
      } else if (msg.state === 'processing') {
        audio.update(s => ({ ...s, micState: 'processing' }));
      } else if (msg.state === 'idle') {
        audio.update(s => ({ ...s, micState: 'idle', speakerState: 'idle', isVadActive: false, wakewordActive: false }));
      }
      break;

    case 'context_size':
      conversation.update(s => ({
        ...s,
        contextChars: Number(msg.chars || 0),
        promptChars: Number(msg.promptChars || 0),
        conversationChars: Number(msg.conversationChars || 0),
        historyTextChars: Number(msg.historyTextChars || 0),
        historyFullChars: Number(msg.historyFullChars || 0),
        proxyMdChars: Number(msg.proxyMdChars || 0),
        compressedChars: Number(msg.compressedChars || 0),
        liveTurnChars: Number(msg.liveTurnChars || 0),
        scratchpadChars: Number(msg.scratchpadChars || 0),
        queuedChars: Number(msg.queuedChars || 0),
      }));
      break;

    case 'audio':
      audioPlayer.playChunk(msg.content, msg.sample_rate || 24000);
      break;
  }
}

export async function sendProxyMessage(text: string) {
  if (!text.trim()) return;

  conversation.update(state => ({
    ...state,
    messages: [...state.messages, {
      id: generateMessageId(),
      role: 'user',
      content: text,
      timestamp: Date.now(),
    }],
  }));

  try {
    await fetch('/api/plan/message', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });
  } catch (e) {
    conversation.update(state => ({
      ...state,
      messages: [...state.messages, {
        id: generateMessageId(),
        role: 'assistant',
        content: 'Failed to send message to proxy agent.',
        timestamp: Date.now(),
      }],
    }));
  }
}

export function sendAudioChunk(base64Pcm16: string, sampleRate = 16000) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({
    type: 'audio_chunk',
    data: base64Pcm16,
    sample_rate: sampleRate,
  }));
}

export function updateVoiceConfig(configUpdate: {
  stt_backend?: string;
  tts?: boolean;
  wakeword?: {
    enabled?: boolean;
    threshold?: number;
    models?: string[];
    active_window_ms?: number;
  };
  vad?: {
    energy_threshold?: number;
    silence_duration_ms?: number;
    min_speech_ms?: number;
  };
}) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type: 'config', ...configUpdate }));
}

export function cancelGeneration() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type: 'cancel' }));
  audioPlayer.stop();
}

export function disconnect() {
  if (ws) {
    ws.close();
    ws = null;
  }

  if (reconnectTimeout) {
    clearTimeout(reconnectTimeout);
    reconnectTimeout = null;
  }
  clearDispatchCountdown();
}
