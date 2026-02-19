import { writable } from 'svelte/store';

export interface SettingsState {
  sttBackend: string;
  ttsEnabled: boolean;
  vadThreshold: number;
  silenceDurationMs: number;
  autoSend: boolean;
  wakewordEnabled: boolean;
  wakewordThreshold: number;
  showSettings: boolean;
}

const defaultSettings: SettingsState = {
  sttBackend: 'moonshine-tiny',
  ttsEnabled: true,
  vadThreshold: 0.5,
  silenceDurationMs: 800,
  autoSend: true,
  wakewordEnabled: true,
  wakewordThreshold: 0.55,
  showSettings: false,
};

// Load from localStorage
const stored = typeof localStorage !== 'undefined' 
  ? localStorage.getItem('jarvis-settings')
  : null;

const initialSettings = stored ? { ...defaultSettings, ...JSON.parse(stored) } : defaultSettings;

export const settings = writable<SettingsState>(initialSettings);

// Persist settings
settings.subscribe(value => {
  if (typeof localStorage !== 'undefined') {
    const { showSettings, ...persistable } = value;
    localStorage.setItem('jarvis-settings', JSON.stringify(persistable));
  }
});
