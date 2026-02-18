import { writable, derived } from 'svelte/store';
import type { ChatMessage, ServerStatus } from '../types/chat';

export const messages = writable<ChatMessage[]>([]);
export const status = writable<ServerStatus>({ connected: false, engine: 'instruct', gpu: false });
export const sttBackends = writable<string[]>([]);
export const selectedStt = writable<string>('moonshine-tiny');
export const ttsEnabled = writable<boolean>(false);
export const isRecording = writable<boolean>(false);
export const isGenerating = writable<boolean>(false);

export const messageCount = derived(messages, $m => $m.length);

let _id = 0;
export function nextId(): string {
  return `msg-${++_id}-${Date.now()}`;
}
