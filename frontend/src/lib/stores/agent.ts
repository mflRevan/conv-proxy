import { writable } from 'svelte/store';

export interface AgentProgressItem {
  id: string;
  state: 'analyzing' | 'running' | 'done' | 'error';
  progress: number;
  title: string;
  content: string;
  timestamp: number;
}

export interface ToolEvent {
  id: string;
  tool: string;
  task?: string;
  timestamp: number;
}

export interface AgentPanelState {
  status: string;
  currentTask: string;
  progressFeed: AgentProgressItem[];
  toolEvents: ToolEvent[];
  queuedTask: string;
  dispatchCountdown: number | null;
  bridgeConfigured: boolean;
  bridgeSessionId: string;
  dispatchEnabled: boolean;
  contextMessages: number;
  contextChars: number;
  pulseToken: number;
}

const initial: AgentPanelState = {
  status: 'idle',
  currentTask: '',
  progressFeed: [],
  toolEvents: [],
  queuedTask: '',
  dispatchCountdown: null,
  bridgeConfigured: false,
  bridgeSessionId: '',
  dispatchEnabled: false,
  contextMessages: 0,
  contextChars: 0,
  pulseToken: 0,
};

export const agentPanel = writable<AgentPanelState>(initial);

let _id = 0;
export function nextAgentId(prefix = 'evt'): string {
  _id += 1;
  return `${prefix}-${Date.now()}-${_id}`;
}
