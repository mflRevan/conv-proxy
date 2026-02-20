import { writable } from 'svelte/store';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
}

export interface ConversationState {
  messages: Message[];
  currentResponse: string;
  isStreaming: boolean;
  taskDraft: string;
  queuedTask: string;
  dispatchCountdown: number | null;
  lastDispatchAt: number | null;
  contextChars: number;
  promptChars: number;
  conversationChars: number;
  historyTextChars: number;
  historyFullChars: number;
  proxyMdChars: number;
  compressedChars: number;
  liveTurnChars: number;
  scratchpadChars: number;
  queuedChars: number;
}

const initialState: ConversationState = {
  messages: [],
  currentResponse: '',
  isStreaming: false,
  taskDraft: '',
  queuedTask: '',
  dispatchCountdown: null,
  lastDispatchAt: null,
  contextChars: 0,
  promptChars: 0,
  conversationChars: 0,
  historyTextChars: 0,
  historyFullChars: 0,
  proxyMdChars: 0,
  compressedChars: 0,
  liveTurnChars: 0,
  scratchpadChars: 0,
  queuedChars: 0,
};

export const conversation = writable<ConversationState>(initialState);

let msgIdCounter = 0;
export function generateMessageId(): string {
  return `msg-${++msgIdCounter}-${Date.now()}`;
}
