import { audio } from '../stores/audio';
import { settings } from '../stores/settings';
import { sendAudio, cancelGeneration } from './websocket';
import { get } from 'svelte/store';

class AudioRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private stream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private animationFrame: number | null = null;
  private silenceTimer: number | null = null;
  private hasSpokenYet = false;

  private readonly SILENCE_DURATION = 1500; // ms
  private readonly MIN_RECORDING_TIME = 500; // ms
  private recordingStartTime = 0;

  async start() {
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      
      // Set up audio analysis
      this.audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
      const source = this.audioContext.createMediaStreamSource(this.stream);
      this.analyser = this.audioContext.createAnalyser();
      this.analyser.fftSize = 256;
      source.connect(this.analyser);

      // Start MediaRecorder
      this.mediaRecorder = new MediaRecorder(this.stream);
      this.audioChunks = [];
      this.hasSpokenYet = false;
      this.recordingStartTime = Date.now();

      this.mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          this.audioChunks.push(event.data);
        }
      };

      this.mediaRecorder.onstop = async () => {
        await this.processRecording();
      };

      this.mediaRecorder.start(100); // Collect data every 100ms
      
      audio.update(state => ({ 
        ...state, 
        micState: 'listening',
        currentTranscription: '',
      }));

      // Start monitoring audio levels
      this.monitorAudioLevel();
      
      // Cancel any ongoing TTS playback
      cancelGeneration();

    } catch (error) {
      console.error('Error starting recording:', error);
      audio.update(state => ({ ...state, micState: 'idle' }));
    }
  }

  stop() {
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop();
    }
    
    this.cleanup();
  }

  private cleanup() {
    if (this.animationFrame) {
      cancelAnimationFrame(this.animationFrame);
      this.animationFrame = null;
    }

    if (this.silenceTimer) {
      clearTimeout(this.silenceTimer);
      this.silenceTimer = null;
    }

    if (this.stream) {
      this.stream.getTracks().forEach(track => track.stop());
      this.stream = null;
    }

    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }

    this.analyser = null;
  }

  private monitorAudioLevel() {
    if (!this.analyser) return;

    const bufferLength = this.analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    const check = () => {
      if (!this.analyser) return;

      this.analyser.getByteFrequencyData(dataArray);
      
      // Calculate average volume
      const sum = dataArray.reduce((a, b) => a + b, 0);
      const average = sum / bufferLength;
      const level = Math.min(100, (average / 255) * 200);

      audio.update(state => ({ ...state, audioLevel: level }));

      // Simple VAD: check if audio is above threshold
      const settingsState = get(settings);
      const threshold = settingsState.vadThreshold * 128; // 0-128 scale
      const isActive = average > threshold;

      audio.update(state => ({ ...state, isVadActive: isActive }));

      // Auto-stop on silence
      if (isActive) {
        this.hasSpokenYet = true;
        
        // Clear silence timer when speech is detected
        if (this.silenceTimer) {
          clearTimeout(this.silenceTimer);
          this.silenceTimer = null;
        }
      } else if (this.hasSpokenYet && !this.silenceTimer) {
        // Start silence timer once we've detected speech and it stops
        const elapsed = Date.now() - this.recordingStartTime;
        
        if (elapsed > this.MIN_RECORDING_TIME) {
          this.silenceTimer = window.setTimeout(() => {
            console.log('Silence detected, stopping recording');
            this.stop();
          }, this.SILENCE_DURATION);
        }
      }

      this.animationFrame = requestAnimationFrame(check);
    };

    check();
  }

  private async processRecording() {
    audio.update(state => ({ 
      ...state, 
      micState: 'processing',
      audioLevel: 0,
      isVadActive: false,
    }));

    try {
      // Combine audio chunks
      const audioBlob = new Blob(this.audioChunks, { type: 'audio/wav' });
      
      // Convert to base64
      const reader = new FileReader();
      reader.readAsDataURL(audioBlob);
      
      reader.onloadend = () => {
        const base64 = (reader.result as string).split(',')[1];
        const settingsState = get(settings);
        
        // Send to server
        sendAudio(base64, settingsState.sttBackend);
        
        audio.update(state => ({ ...state, micState: 'idle' }));
      };

    } catch (error) {
      console.error('Error processing recording:', error);
      audio.update(state => ({ ...state, micState: 'idle' }));
    }
  }
}

export const audioRecorder = new AudioRecorder();
