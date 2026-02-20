import { writable } from 'svelte/store';

export interface ToolCall {
  name: string;
  arguments?: string;
  result?: string;
  status?: string;
}

export interface AgentState {
  status: 'idle' | 'busy' | 'error';
  currentTool: string;
  currentArgs: string;
  assistantStream: string;
  thinking: string;
  lastSummary: string;
  toolCalls: ToolCall[];
}

const initial: AgentState = {
  status: 'idle',
  currentTool: '',
  currentArgs: '',
  assistantStream: '',
  thinking: '',
  lastSummary: '',
  toolCalls: [],
};

export const agentState = writable<AgentState>(initial);
