const chat = document.getElementById('chat');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send');
const statusEl = document.getElementById('status');
const ttsToggle = document.getElementById('ttsToggle');
const micBtn = document.getElementById('mic');
const recordingIndicator = document.getElementById('recordingIndicator');
const sttSelect = document.getElementById('sttSelect');

let ws;
let currentAssistant;
let currentTiming = null;
let audioQueue = [];
let audioCtx;
let mediaRecorder;
let mediaStream;
let recognition;
let recording = false;

function setStatus(online) {
  statusEl.textContent = online ? 'online' : 'offline';
  statusEl.classList.toggle('online', online);
}

function addMessage(text, role) {
  const div = document.createElement('div');
  div.className = `message ${role}`;
  div.textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

function ensureLatencyLabel(messageEl) {
  let span = messageEl.querySelector('.latency');
  if (!span) {
    span = document.createElement('span');
    span.className = 'latency';
    messageEl.appendChild(span);
  }
  return span;
}

function connect() {
  ws = new WebSocket(`ws://${window.location.host}/ws/chat`);

  ws.onopen = () => setStatus(true);
  ws.onclose = () => setStatus(false);

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'text') {
      if (!currentAssistant) {
        currentAssistant = addMessage('', 'assistant');
        currentTiming = { start: performance.now(), ttft: null };
      }
      if (currentTiming && currentTiming.ttft === null) {
        currentTiming.ttft = performance.now() - currentTiming.start;
      }
      currentAssistant.textContent += data.content;
      chat.scrollTop = chat.scrollHeight;
    } else if (data.type === 'audio') {
      enqueueAudio(data.content, data.sample_rate);
    } else if (data.type === 'done') {
      if (currentAssistant && currentTiming) {
        const total = performance.now() - currentTiming.start;
        const latencyLabel = ensureLatencyLabel(currentAssistant);
        const ttft = currentTiming.ttft ? `${currentTiming.ttft.toFixed(0)}ms` : 'n/a';
        latencyLabel.textContent = `TTFT ${ttft} • total ${total.toFixed(0)}ms`;
      }
      currentAssistant = null;
      currentTiming = null;
    } else if (data.type === 'stt') {
      if (data.text) {
        input.value = data.text;
        sendMessage();
      }
    }
  };
}

function enqueueAudio(b64, sampleRate) {
  if (!b64) return;
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  audioQueue.push({ bytes, sampleRate });
  if (!audioCtx) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  if (audioQueue.length === 1) {
    playNext();
  }
}

function playNext() {
  if (audioQueue.length === 0) return;
  const { bytes, sampleRate } = audioQueue[0];
  const buffer = audioCtx.createBuffer(1, bytes.length / 2, sampleRate);
  const channel = buffer.getChannelData(0);
  const view = new DataView(bytes.buffer);
  for (let i = 0; i < channel.length; i++) {
    channel[i] = view.getInt16(i * 2, true) / 32768;
  }
  const source = audioCtx.createBufferSource();
  source.buffer = buffer;
  source.connect(audioCtx.destination);
  source.onended = () => {
    audioQueue.shift();
    playNext();
  };
  source.start(0);
}

function sendMessage() {
  const text = input.value.trim();
  if (!text) return;
  addMessage(text, 'user');
  ws.send(JSON.stringify({ message: text, tts: ttsToggle.checked }));
  input.value = '';
}

async function loadSttBackends() {
  try {
    const res = await fetch('/api/stt/backends');
    const payload = await res.json();
    const backends = payload.backends || [];
    sttSelect.innerHTML = '';
    backends.forEach((name) => {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      sttSelect.appendChild(opt);
    });
    const defaultBackend = payload.default || backends[0];
    if (defaultBackend) {
      sttSelect.value = defaultBackend;
    }
  } catch (err) {
    console.warn('Failed to load STT backends', err);
  }
}

function setRecording(active) {
  recording = active;
  micBtn.classList.toggle('active', active);
  recordingIndicator.classList.toggle('active', active);
}

async function toggleRecording() {
  if (recording) {
    stopRecording();
    return;
  }
  const backend = sttSelect.value;
  if (backend === 'browser') {
    startBrowserRecognition();
  } else {
    await startMediaRecorder();
  }
}

function startBrowserRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    alert('Browser SpeechRecognition API not available in this browser.');
    return;
  }
  recognition = new SpeechRecognition();
  recognition.lang = 'en-US';
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  recognition.onstart = () => setRecording(true);
  recognition.onend = () => setRecording(false);
  recognition.onerror = () => setRecording(false);
  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    input.value = transcript;
    sendMessage();
  };
  recognition.start();
}

async function startMediaRecorder() {
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(mediaStream);
    const chunks = [];
    mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
    mediaRecorder.onstop = async () => {
      const blob = new Blob(chunks, { type: 'audio/webm' });
      const wavBuffer = await convertToWav(blob);
      const b64 = bufferToBase64(wavBuffer);
      ws.send(JSON.stringify({ type: 'audio', data: b64, stt_backend: sttSelect.value }));
      cleanupMedia();
      setRecording(false);
    };
    mediaRecorder.start();
    setRecording(true);
  } catch (err) {
    console.error('Mic error', err);
    setRecording(false);
  }
}

function stopRecording() {
  if (recognition) {
    recognition.stop();
    recognition = null;
  }
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
  }
}

function cleanupMedia() {
  if (mediaStream) {
    mediaStream.getTracks().forEach(track => track.stop());
    mediaStream = null;
  }
  mediaRecorder = null;
}

async function convertToWav(blob) {
  const arrayBuffer = await blob.arrayBuffer();
  if (!audioCtx) {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  }
  const decoded = await audioCtx.decodeAudioData(arrayBuffer);
  const offline = new OfflineAudioContext(1, decoded.duration * 16000, 16000);
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.connect(offline.destination);
  source.start(0);
  const rendered = await offline.startRendering();
  const samples = rendered.getChannelData(0);
  return encodeWav(samples, 16000);
}

function encodeWav(samples, sampleRate) {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);

  function writeString(offset, str) {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  }

  writeString(0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(36, 'data');
  view.setUint32(40, samples.length * 2, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }
  return buffer;
}

function bufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

sendBtn.addEventListener('click', sendMessage);
input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') sendMessage();
});
micBtn.addEventListener('click', toggleRecording);

loadSttBackends();
connect();
