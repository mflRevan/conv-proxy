import { writable } from 'svelte/store';

export interface SettingsState {
  proxyModel: string;
  proxyTemperature: number;
  proxyMaxTokens: number;
  historyLength: number;
  compressedContext: string;
  compressedContextEnabled: boolean;
  mainHistoryLength: number;
  mainHistoryFullCount: number;

  sttBackend: string;
  ttsEnabled: boolean;
  vadThreshold: number;
  silenceDurationMs: number;
  autoSend: boolean;
  wakewordEnabled: boolean;
  wakewordThreshold: number;
  wakewordActiveWindowMs: number;

  gatewayUrl: string;
  gatewayToken: string;

  showSettings: boolean;
}

const defaultSettings: SettingsState = {
  proxyModel: 'openai/gpt-oss-120b',
  proxyTemperature: 0.3,
  proxyMaxTokens: 300,
  historyLength: 15,
  compressedContext: '',
  compressedContextEnabled: false,
  mainHistoryLength: 20,
  mainHistoryFullCount: 5,

  sttBackend: 'whisper-small',
  ttsEnabled: true,
  vadThreshold: 0.5,
  silenceDurationMs: 800,
  autoSend: true,
  wakewordEnabled: true,
  wakewordThreshold: 0.55,
  wakewordActiveWindowMs: 10000,

  gatewayUrl: '',
  gatewayToken: '',

  showSettings: false,
};

const stored = typeof localStorage !== 'undefined'
  ? localStorage.getItem('jarvis-settings')
  : null;

const initialSettings = stored ? { ...defaultSettings, ...JSON.parse(stored) } : defaultSettings;

export const settings = writable<SettingsState>(initialSettings);

settings.subscribe(value => {
  if (typeof localStorage !== 'undefined') {
    const { showSettings, ...persistable } = value;
    localStorage.setItem('jarvis-settings', JSON.stringify(persistable));
  }
});
