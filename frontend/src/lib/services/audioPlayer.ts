import { audio } from '../stores/audio';

class AudioPlayer {
  private audioContext: AudioContext | null = null;
  private audioQueue: AudioBuffer[] = [];
  private isPlaying = false;
  private currentSource: AudioBufferSourceNode | null = null;

  constructor() {
    if (typeof window !== 'undefined') {
      this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
    }
  }

  async playChunk(base64Data: string, sampleRate: number) {
    if (!this.audioContext) return;

    if (this.audioContext.state === 'suspended') {
      try { await this.audioContext.resume(); } catch {}
    }

    audio.update(state => ({ ...state, speakerState: 'speaking' }));

    try {
      // Decode base64 PCM16 data
      const binaryString = atob(base64Data);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }

      // Convert PCM16 to Float32
      const pcm16 = new Int16Array(bytes.buffer);
      const float32 = new Float32Array(pcm16.length);
      for (let i = 0; i < pcm16.length; i++) {
        float32[i] = pcm16[i] / 32768.0;
      }

      // Create audio buffer
      const audioBuffer = this.audioContext.createBuffer(
        1,
        float32.length,
        sampleRate
      );
      audioBuffer.getChannelData(0).set(float32);

      this.audioQueue.push(audioBuffer);
      
      if (!this.isPlaying) {
        this.playNext();
      }
    } catch (error) {
      console.error('Error playing audio chunk:', error);
      audio.update(state => ({ ...state, speakerState: 'idle' }));
    }
  }

  private playNext() {
    if (this.audioQueue.length === 0) {
      this.isPlaying = false;
      audio.update(state => ({ ...state, speakerState: 'idle' }));
      return;
    }

    if (!this.audioContext) return;

    this.isPlaying = true;
    const buffer = this.audioQueue.shift()!;
    
    const source = this.audioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(this.audioContext.destination);
    
    source.onended = () => {
      this.currentSource = null;
      this.playNext();
    };

    this.currentSource = source;
    source.start();
  }

  stop() {
    if (this.currentSource) {
      try {
        this.currentSource.stop();
        this.currentSource = null;
      } catch (e) {
        // Already stopped
      }
    }
    
    this.audioQueue = [];
    this.isPlaying = false;
    audio.update(state => ({ ...state, speakerState: 'idle' }));
  }
}

export const audioPlayer = new AudioPlayer();
