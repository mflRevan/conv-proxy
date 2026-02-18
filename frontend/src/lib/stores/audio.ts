import { writable } from 'svelte/store';

export type MicState = 'idle' | 'listening' | 'processing';
export type SpeakerState = 'idle' | 'speaking';

export interface AudioState {
  micState: MicState;
  speakerState: SpeakerState;
  audioLevel: number; // 0-100
  isVadActive: boolean;
  currentTranscription: string;
}

const initialState: AudioState = {
  micState: 'idle',
  speakerState: 'idle',
  audioLevel: 0,
  isVadActive: false,
  currentTranscription: '',
};

export const audio = writable<AudioState>(initialState);
