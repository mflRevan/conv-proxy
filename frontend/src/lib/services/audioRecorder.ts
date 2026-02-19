import { audio } from '../stores/audio';
import { settings } from '../stores/settings';
import { sendAudioChunk, cancelGeneration, updateVoiceConfig } from './websocket';
import { get } from 'svelte/store';

function floatToPcm16Base64(input: Float32Array): string {
  const pcm = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]));
    pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  const bytes = new Uint8Array(pcm.buffer);
  let binary = '';
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

class AudioRecorder {
  private stream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private sourceNode: MediaStreamAudioSourceNode | null = null;
  private processorNode: ScriptProcessorNode | null = null;

  private running = false;
  private readonly targetSampleRate = 16000;

  async start() {
    if (this.running) return;

    try {
      const s = get(settings);

      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
        },
      });

      this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      this.sourceNode = this.audioContext.createMediaStreamSource(this.stream);
      this.processorNode = this.audioContext.createScriptProcessor(2048, 1, 1);

      const sourceRate = this.audioContext.sampleRate;
      const downsampleRatio = sourceRate / this.targetSampleRate;

      this.processorNode.onaudioprocess = (event) => {
        if (!this.running) return;
        const input = event.inputBuffer.getChannelData(0);

        // light local RMS for UI feedback only
        let sum = 0;
        for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
        const rms = Math.sqrt(sum / input.length);
        const level = Math.min(100, rms * 450);

        audio.update(state => ({
          ...state,
          micState: 'listening',
          audioLevel: level,
          isVadActive: rms > (s.vadThreshold * 0.06),
        }));

        // downsample to 16k mono
        const outLen = Math.floor(input.length / downsampleRatio);
        const out = new Float32Array(outLen);
        for (let i = 0; i < outLen; i++) {
          const idx = Math.floor(i * downsampleRatio);
          out[i] = input[idx] || 0;
        }

        sendAudioChunk(floatToPcm16Base64(out), this.targetSampleRate);
      };

      this.sourceNode.connect(this.processorNode);
      // connect to destination keeps processor alive in some browsers
      this.processorNode.connect(this.audioContext.destination);

      // Sync backend runtime config
      updateVoiceConfig({
        stt_backend: s.sttBackend,
        tts: s.ttsEnabled,
        wakeword: {
          enabled: s.wakewordEnabled,
          threshold: s.wakewordThreshold,
          models: ['hey jarvis'],
        },
        vad: {
          energy_threshold: Math.max(0.005, s.vadThreshold * 0.04),
          silence_duration_ms: s.silenceDurationMs,
          min_speech_ms: 250,
        },
      });

      this.running = true;
      audio.update(state => ({ ...state, micState: 'listening', currentTranscription: '' }));

      // barge-in: cancel any ongoing generation immediately on mic start
      cancelGeneration();
    } catch (error) {
      console.error('Error starting streaming recorder:', error);
      this.stop();
    }
  }

  stop() {
    this.running = false;

    if (this.processorNode) {
      try { this.processorNode.disconnect(); } catch {}
      this.processorNode.onaudioprocess = null;
      this.processorNode = null;
    }
    if (this.sourceNode) {
      try { this.sourceNode.disconnect(); } catch {}
      this.sourceNode = null;
    }
    if (this.stream) {
      this.stream.getTracks().forEach(t => t.stop());
      this.stream = null;
    }
    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }

    audio.update(state => ({
      ...state,
      micState: 'idle',
      audioLevel: 0,
      isVadActive: false,
    }));
  }
}

export const audioRecorder = new AudioRecorder();
