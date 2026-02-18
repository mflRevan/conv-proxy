import { writable } from 'svelte/store';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  reasoning?: string;
  isStreaming?: boolean;
}

export interface ConversationState {
  messages: Message[];
  currentResponse: string;
  currentReasoning: string;
  isStreaming: boolean;
  taskDraft: string;
}

const initialState: ConversationState = {
  messages: [],
  currentResponse: '',
  currentReasoning: '',
  isStreaming: false,
  taskDraft: '',
};

export const conversation = writable<ConversationState>(initialState);

let msgIdCounter = 0;
export function generateMessageId(): string {
  return `msg-${++msgIdCounter}-${Date.now()}`;
}
