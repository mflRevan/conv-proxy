<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { isRecording, selectedStt, isGenerating } from '../stores/chat';
  import { transcribeAudio } from '../services/api';

  const dispatch = createEventDispatcher();

  let inputText = '';
  let mediaRecorder: MediaRecorder | null = null;
  let mediaStream: MediaStream | null = null;
  let audioCtx: AudioContext | null = null;

  function handleSend() {
    const text = inputText.trim();
    if (!text) return;
    dispatch('send', text);
    inputText = '';
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  async function toggleRecording() {
    if ($isRecording) {
      stopRecording();
      return;
    }

    const backend = $selectedStt;
    if (backend === 'browser') {
      startBrowserSpeech();
    } else {
      await startMediaRecorder();
    }
  }

  function startBrowserSpeech() {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) { alert('Browser Speech API not available.'); return; }
    const recognition = new SR();
    recognition.lang = 'en-US';
    recognition.interimResults = false;
    recognition.onstart = () => isRecording.set(true);
    recognition.onend = () => isRecording.set(false);
    recognition.onerror = () => isRecording.set(false);
    recognition.onresult = (e: any) => {
      const text = e.results[0][0].transcript;
      if (text) dispatch('send', text);
    };
    recognition.start();
  }

  async function startMediaRecorder() {
    if (!navigator.mediaDevices?.getUserMedia) {
      alert('Microphone not available.\nUse "browser" STT or access via localhost/HTTPS.');
      return;
    }
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(mediaStream);
      const chunks: Blob[] = [];
      mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
      mediaRecorder.onstop = async () => {
        isRecording.set(false);
        const blob = new Blob(chunks, { type: 'audio/webm' });
        const wav = await convertToWav(blob);
        const text = await transcribeAudio(wav, $selectedStt);
        if (text) dispatch('send', text);
        cleanup();
      };
      mediaRecorder.start();
      isRecording.set(true);
    } catch (err: any) {
      alert(`Mic error: ${err.message}`);
      isRecording.set(false);
    }
  }

  function stopRecording() {
    if (mediaRecorder?.state !== 'inactive') mediaRecorder?.stop();
    isRecording.set(false);
  }

  function cleanup() {
    mediaStream?.getTracks().forEach(t => t.stop());
    mediaStream = null;
    mediaRecorder = null;
  }

  async function convertToWav(blob: Blob): Promise<ArrayBuffer> {
    const ab = await blob.arrayBuffer();
    if (!audioCtx) audioCtx = new AudioContext();
    const decoded = await audioCtx.decodeAudioData(ab);
    const offline = new OfflineAudioContext(1, decoded.duration * 16000, 16000);
    const src = offline.createBufferSource();
    src.buffer = decoded;
    src.connect(offline.destination);
    src.start(0);
    const rendered = await offline.startRendering();
    return encodeWav(rendered.getChannelData(0), 16000);
  }

  function encodeWav(samples: Float32Array, sr: number): ArrayBuffer {
    const buf = new ArrayBuffer(44 + samples.length * 2);
    const v = new DataView(buf);
    const w = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
    w(0, 'RIFF'); v.setUint32(4, 36 + samples.length * 2, true); w(8, 'WAVE');
    w(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
    v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
    w(36, 'data'); v.setUint32(40, samples.length * 2, true);
    let o = 44;
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      v.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7FFF, true); o += 2;
    }
    return buf;
  }
</script>

<footer class="input-bar">
  <div class="rec-dot" class:active={$isRecording}></div>
  <button class="mic-btn" class:active={$isRecording} on:click={toggleRecording} title="Voice input">
    {#if $isRecording}⏹{:else}🎙️{/if}
  </button>
  <input
    type="text"
    class="chat-input"
    bind:value={inputText}
    on:keydown={handleKeydown}
    placeholder={$isGenerating ? 'Thinking…' : 'Ask Jarvis…'}
    disabled={$isGenerating}
  />
  <button class="send-btn" on:click={handleSend} disabled={$isGenerating || !inputText.trim()}>
    {#if $isGenerating}
      <span class="spinner"></span>
    {:else}
      ➤
    {/if}
  </button>
</footer>

<style>
  .input-bar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 14px 20px;
    border-top: 1px solid rgba(255,255,255,0.06);
    background: #0d1117;
  }
  .rec-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: #334155; flex-shrink: 0;
    transition: all 0.2s;
  }
  .rec-dot.active {
    background: #ef4444;
    box-shadow: 0 0 8px rgba(239,68,68,0.6);
    animation: pulse 1.2s infinite;
  }
  @keyframes pulse {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.3); }
  }
  .mic-btn {
    width: 40px; height: 40px;
    border-radius: 10px;
    border: 1px solid rgba(255,255,255,0.08);
    background: transparent;
    color: #e2e8f0;
    cursor: pointer;
    font-size: 1rem;
    display: grid; place-items: center;
    transition: all 0.15s;
  }
  .mic-btn:hover { border-color: rgba(255,255,255,0.2); }
  .mic-btn.active { border-color: #ef4444; color: #ef4444; }
  .chat-input {
    flex: 1;
    padding: 10px 14px;
    border-radius: 10px;
    border: 1px solid rgba(255,255,255,0.08);
    background: #0a0e14;
    color: #e2e8f0;
    font-size: 0.9rem;
    outline: none;
    transition: border-color 0.15s;
  }
  .chat-input:focus { border-color: rgba(125,211,252,0.3); }
  .chat-input:disabled { opacity: 0.5; }
  .send-btn {
    width: 44px; height: 44px;
    border-radius: 12px;
    border: none;
    background: linear-gradient(135deg, #22c55e, #16a34a);
    color: #fff;
    font-size: 1.1rem;
    cursor: pointer;
    display: grid; place-items: center;
    transition: all 0.15s;
  }
  .send-btn:disabled { opacity: 0.4; cursor: default; }
  .send-btn:not(:disabled):hover { transform: scale(1.05); }
  .spinner {
    width: 16px; height: 16px;
    border: 2px solid rgba(255,255,255,0.3);
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
