export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  text: string;
  thinking?: string;
  toolCalls?: ToolCall[];
  audio?: string[];
  sampleRate?: number;
  ttft?: number;
  totalMs?: number;
  timestamp: number;
}

export interface ToolCall {
  name: string;
  args: Record<string, unknown>;
  result?: string;
}

export interface SttBackend {
  name: string;
}

export interface ServerStatus {
  connected: boolean;
  engine: string;
  gpu: boolean;
}

export interface ChatResponse {
  text: string;
  thinking?: string;
  toolCalls?: ToolCall[];
  audio?: string[];
  sample_rate?: number;
  error?: string;
}
