import { writable, derived } from 'svelte/store';

export interface ConnectionState {
  ws: WebSocket | null;
  status: 'disconnected' | 'connecting' | 'connected' | 'error';
  gatewayState: 'disconnected' | 'connecting' | 'connected' | 'error' | 'disabled';
  proxyModel: string;
  reconnectAttempts: number;
}

const initialState: ConnectionState = {
  ws: null,
  status: 'disconnected',
  gatewayState: 'disconnected',
  proxyModel: '',
  reconnectAttempts: 0,
};

export const connection = writable<ConnectionState>(initialState);

export const isConnected = derived(
  connection,
  $conn => $conn.status === 'connected'
);
