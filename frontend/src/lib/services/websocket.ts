import { connection } from '../stores/connection';
import { conversation, generateMessageId } from '../stores/conversation';
import { audio } from '../stores/audio';
import { get } from 'svelte/store';
import { audioPlayer } from './audioPlayer';
import { agentPanel, nextAgentId } from '../stores/agent';

const WS_URL = `ws://${window.location.host}/ws/voice`;
const BASE_RECONNECT_DELAY = 800;
const MAX_RECONNECT_DELAY = 10000;
const MAX_RECONNECT_ATTEMPTS = 12;

let ws: WebSocket | null = null;
let reconnectTimeout: number | null = null;
let dispatchTimer: number | null = null;

function clearDispatchCountdown() {
  if (dispatchTimer) {
    clearInterval(dispatchTimer);
    dispatchTimer = null;
  }
  agentPanel.update(s => ({ ...s, dispatchCountdown: null }));
}

function startDispatchCountdown(seconds = 10) {
  clearDispatchCountdown();
  let remaining = seconds;
  agentPanel.update(s => ({ ...s, dispatchCountdown: remaining }));
  dispatchTimer = window.setInterval(() => {
    remaining -= 1;
    if (remaining <= 0) {
      clearDispatchCountdown();
      return;
    }
    agentPanel.update(s => ({ ...s, dispatchCountdown: remaining }));
  }, 1000);
}

function reconnectDelayMs(attempt: number): number {
  const exp = Math.min(MAX_RECONNECT_DELAY, BASE_RECONNECT_DELAY * Math.pow(2, attempt));
  const jitter = Math.floor(Math.random() * 250);
  return exp + jitter;
}

export function connect() {
  const connState = get(connection);
  if (connState.ws?.readyState === WebSocket.OPEN || connState.ws?.readyState === WebSocket.CONNECTING) {
    return;
  }

  connection.update(state => ({ ...state, status: 'connecting' }));

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

      fetch('/api/bridge/status')
        .then(r => r.json())
        .then(data => {
          agentPanel.update(s => ({
            ...s,
            bridgeConfigured: !!data.configured,
            bridgeSessionId: data.session_id || '',
            dispatchEnabled: !!data.dispatch_enabled || false,
            contextMessages: Number(data.context_messages || 0),
            contextChars: Number(data.context_chars || 0),
          }));
        })
        .catch(() => {});
    };

    ws.onmessage = (event) => {
      try {
        handleMessage(JSON.parse(event.data));
      } catch (e) {
        console.error('Invalid WS message:', e);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      connection.update(state => ({ ...state, status: 'error' }));
    };

    ws.onclose = () => {
      connection.update(state => ({
        ...state,
        ws: null,
        status: 'disconnected',
      }));

      audioPlayer.stop();
      clearDispatchCountdown();

      const s = get(connection);
      if (s.reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        const delay = reconnectDelayMs(s.reconnectAttempts);
        reconnectTimeout = window.setTimeout(() => {
          connection.update(state => ({
            ...state,
            reconnectAttempts: state.reconnectAttempts + 1,
          }));
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
    case 'status':
      connection.update(state => ({
        ...state,
        model: msg.model || state.model,
        agentStatus: msg.agent_status || state.agentStatus,
      }));
      if (msg.task_draft !== undefined) {
        conversation.update(state => ({ ...state, taskDraft: msg.task_draft || '' }));
      }
      agentPanel.update(s => ({
        ...s,
        status: msg.agent_status || s.status,
        queuedTask: msg.queued_task || s.queuedTask,
        bridgeConfigured: !!msg.bridge?.configured || s.bridgeConfigured,
        bridgeSessionId: msg.bridge?.session_id || s.bridgeSessionId,
        dispatchEnabled: !!msg.bridge?.dispatch_enabled || s.dispatchEnabled,
        contextMessages: Number(msg.bridge?.context_messages || s.contextMessages || 0),
        contextChars: Number(msg.bridge?.context_chars || s.contextChars || 0),
      }));
      break;

    case 'state':
      if (msg.state === 'listening') {
        audio.update(s => ({ ...s, micState: 'listening' }));
      } else if (msg.state === 'processing') {
        audio.update(s => ({ ...s, micState: 'processing' }));
      } else if (msg.state === 'speaking') {
        audio.update(s => ({ ...s, speakerState: 'speaking' }));
      } else if (msg.state === 'idle') {
        audio.update(s => ({ ...s, micState: 'idle', speakerState: 'idle', isVadActive: false }));
      }
      break;

    case 'vad':
      audio.update(s => ({ ...s, isVadActive: msg.event === 'speech_start' || msg.event === 'barge_in' }));
      if (msg.event === 'speech_start' || msg.event === 'barge_in') {
        audioPlayer.stop();
        cancelGeneration();
      }
      break;

    case 'transcription':
      audio.update(state => ({
        ...state,
        currentTranscription: msg.text || '',
      }));

      if (msg.final && msg.text) {
        conversation.update(state => ({
          ...state,
          messages: [
            ...state.messages,
            {
              id: generateMessageId(),
              role: 'user',
              content: msg.text,
              timestamp: Date.now(),
            },
          ],
        }));
      }
      break;

    case 'text':
      conversation.update(state => ({
        ...state,
        currentResponse: state.currentResponse + (msg.content || ''),
        isStreaming: true,
      }));
      break;

    case 'reasoning':
      conversation.update(state => ({
        ...state,
        currentReasoning: state.currentReasoning + (msg.content || ''),
      }));
      break;

    case 'action':
      conversation.update(state => ({
        ...state,
        taskDraft: msg.task_draft ?? state.taskDraft,
      }));
      agentPanel.update(s => ({
        ...s,
        queuedTask: msg.queued_task ?? s.queuedTask,
        pulseToken: Date.now(),
      }));
      if (msg.action === 'queued' && msg.queued_task) {
        startDispatchCountdown(10);
      } else if (msg.action === 'buffer' || msg.action === 'buffer_cleared' || msg.action === 'stop') {
        clearDispatchCountdown();
      }
      break;

    case 'audio':
      audioPlayer.playChunk(msg.content, msg.sample_rate || 24000);
      break;

    case 'agent_status':
      agentPanel.update(s => ({
        ...s,
        status: msg.status || s.status,
        currentTask: msg.current_task || '',
      }));
      if (msg.status === 'busy') clearDispatchCountdown();
      break;

    case 'agent_progress':
      agentPanel.update(s => ({
        ...s,
        progressFeed: [
          ...s.progressFeed,
          {
            id: nextAgentId('progress'),
            state: msg.state || 'running',
            progress: Number(msg.progress || 0),
            title: msg.title || 'Update',
            content: msg.content || '',
            timestamp: Date.now(),
          },
        ].slice(-20),
      }));
      break;

    case 'tool_called':
      agentPanel.update(s => ({
        ...s,
        pulseToken: Date.now(),
        toolEvents: [
          {
            id: nextAgentId('tool'),
            tool: msg.tool || 'unknown',
            task: msg.task || '',
            timestamp: Date.now(),
          },
          ...s.toolEvents,
        ].slice(0, 12),
      }));
      break;

    case 'agent_brief':
      if (msg.content) {
        conversation.update(state => ({
          ...state,
          messages: [
            ...state.messages,
            {
              id: generateMessageId(),
              role: 'assistant',
              content: msg.content,
              timestamp: Date.now(),
            },
          ],
        }));
      }
      clearDispatchCountdown();
      break;

    case 'dispatch_ready':
      clearDispatchCountdown();
      agentPanel.update(s => ({ ...s, queuedTask: msg.task || s.queuedTask, pulseToken: Date.now() }));
      break;

    case 'context_size':
      agentPanel.update(s => ({ ...s, contextMessages: Number(msg.messages || 0), contextChars: Number(msg.chars || 0) }));
      break;
    case 'bridge_status':
      agentPanel.update(s => ({
        ...s,
        bridgeConfigured: !!msg.configured,
        bridgeSessionId: msg.session_id || '',
        dispatchEnabled: !!msg.dispatch_enabled || false,
      }));
      break;


    case 'done': {
      const convState = get(conversation);
      if (convState.currentResponse) {
        conversation.update(state => ({
          ...state,
          messages: [
            ...state.messages,
            {
              id: generateMessageId(),
              role: 'assistant',
              content: state.currentResponse,
              timestamp: Date.now(),
              reasoning: state.currentReasoning || undefined,
            },
          ],
          currentResponse: '',
          currentReasoning: '',
          isStreaming: false,
          taskDraft: msg.task_draft || state.taskDraft,
        }));
      }

      connection.update(state => ({
        ...state,
        agentStatus: msg.agent_status || state.agentStatus,
      }));
      agentPanel.update(s => ({
        ...s,
        status: msg.agent_status || s.status,
        queuedTask: msg.queued_task ?? s.queuedTask,
        bridgeConfigured: !!msg.bridge?.configured || s.bridgeConfigured,
        bridgeSessionId: msg.bridge?.session_id || s.bridgeSessionId,
        dispatchEnabled: !!msg.bridge?.dispatch_enabled || s.dispatchEnabled,
        contextMessages: Number(msg.bridge?.context_messages || s.contextMessages || 0),
        contextChars: Number(msg.bridge?.context_chars || s.contextChars || 0),
      }));
      if (msg.queued_task && msg.agent_status === 'idle') {
        startDispatchCountdown(10);
      } else if (!msg.queued_task || msg.agent_status === 'busy') {
        clearDispatchCountdown();
      }
      break;
    }

    case 'cancelled':
      conversation.update(state => ({
        ...state,
        currentResponse: '',
        currentReasoning: '',
        isStreaming: false,
      }));
      audioPlayer.stop();
      break;

    case 'error':
      console.error('WS error event:', msg.message || msg.content || msg);
      break;
  }
}

export function sendMessage(text: string) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;

  ws.send(JSON.stringify({ type: 'text', message: text }));

  conversation.update(state => ({
    ...state,
    messages: [
      ...state.messages,
      {
        id: generateMessageId(),
        role: 'user',
        content: text,
        timestamp: Date.now(),
      },
    ],
  }));
}

export function sendAudioChunk(base64Pcm16: string, sampleRate = 16000) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({
    type: 'audio_chunk',
    data: base64Pcm16,
    sample_rate: sampleRate,
  }));
}

export function updateVoiceConfig(config: {
  stt_backend?: string;
  tts?: boolean;
  wakeword?: {
    enabled?: boolean;
    threshold?: number;
    models?: string[];
  };
  vad?: {
    energy_threshold?: number;
    silence_duration_ms?: number;
    min_speech_ms?: number;
  };
}) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type: 'config', ...config }));
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
