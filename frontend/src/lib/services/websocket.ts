import { connection } from '../stores/connection';
import { conversation, generateMessageId } from '../stores/conversation';
import { audio } from '../stores/audio';
import { get } from 'svelte/store';
import { audioPlayer } from './audioPlayer';

const WS_URL = `ws://${window.location.host}/ws/chat`;
const RECONNECT_DELAY = 2000;
const MAX_RECONNECT_ATTEMPTS = 10;

let ws: WebSocket | null = null;
let reconnectTimeout: number | null = null;

export function connect() {
  const connState = get(connection);
  
  if (connState.ws?.readyState === WebSocket.OPEN) {
    return;
  }

  connection.update(state => ({
    ...state,
    status: 'connecting',
  }));

  try {
    ws = new WebSocket(WS_URL);
    
    ws.onopen = () => {
      console.log('WebSocket connected');
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
    };

    ws.onmessage = (event) => {
      handleMessage(JSON.parse(event.data));
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      connection.update(state => ({
        ...state,
        status: 'error',
      }));
    };

    ws.onclose = () => {
      console.log('WebSocket closed');
      connection.update(state => ({
        ...state,
        ws: null,
        status: 'disconnected',
      }));
      
      audioPlayer.stop();
      
      const connState = get(connection);
      if (connState.reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        reconnectTimeout = window.setTimeout(() => {
          connection.update(state => ({
            ...state,
            reconnectAttempts: state.reconnectAttempts + 1,
          }));
          connect();
        }, RECONNECT_DELAY);
      }
    };

    connection.update(state => ({ ...state, ws }));
  } catch (error) {
    console.error('Failed to create WebSocket:', error);
    connection.update(state => ({
      ...state,
      status: 'error',
    }));
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
      break;

    case 'text':
      conversation.update(state => ({
        ...state,
        currentResponse: state.currentResponse + msg.content,
        isStreaming: true,
      }));
      break;

    case 'reasoning':
      conversation.update(state => ({
        ...state,
        currentReasoning: state.currentReasoning + msg.content,
      }));
      break;

    case 'action':
      if (msg.task_draft) {
        conversation.update(state => ({
          ...state,
          taskDraft: msg.task_draft,
        }));
      }
      break;

    case 'audio':
      // Decode and play PCM16 audio
      audioPlayer.playChunk(msg.content, msg.sample_rate || 24000);
      break;

    case 'stt':
      // Transcription from server
      audio.update(state => ({
        ...state,
        currentTranscription: msg.text,
      }));
      
      // Add user message
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
      break;

    case 'done':
      // Finalize assistant message
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
      break;

    case 'cancelled':
      conversation.update(state => ({
        ...state,
        currentResponse: '',
        currentReasoning: '',
        isStreaming: false,
      }));
      audioPlayer.stop();
      break;
  }
}

export function sendMessage(text: string, tts: boolean = true) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.error('WebSocket not connected');
    return;
  }

  ws.send(JSON.stringify({
    type: 'message',
    message: text,
    tts,
  }));

  // Add user message immediately
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

export function sendAudio(audioData: string, sttBackend: string) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    console.error('WebSocket not connected');
    return;
  }

  ws.send(JSON.stringify({
    type: 'audio',
    data: audioData,
    stt_backend: sttBackend,
  }));
}

export function cancelGeneration() {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    return;
  }

  ws.send(JSON.stringify({
    type: 'cancel',
  }));

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
}
