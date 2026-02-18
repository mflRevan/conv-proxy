import { writable, derived } from 'svelte/store';

export interface ConnectionState {
  ws: WebSocket | null;
  status: 'disconnected' | 'connecting' | 'connected' | 'error';
  model: string;
  agentStatus: string;
  reconnectAttempts: number;
}

const initialState: ConnectionState = {
  ws: null,
  status: 'disconnected',
  model: '',
  agentStatus: 'idle',
  reconnectAttempts: 0,
};

export const connection = writable<ConnectionState>(initialState);

export const isConnected = derived(
  connection,
  $conn => $conn.status === 'connected'
);
